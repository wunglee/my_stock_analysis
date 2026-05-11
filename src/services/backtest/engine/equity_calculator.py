"""权益计算器

基于信号序列模拟交易、计算费用、生成权益曲线。

**有意识取舍**：当前费用模型按市场（cn/hk/us）统一费率，不区分板块（科创板/北交所等）
或券商差异。当前仅 A 股主板的费率为精确值（买入 0.03%、卖出 0.13% 含印花税），
港股/美股为占位值。精确费用模型可后续扩展。
"""

from typing import Literal, Optional, Protocol

import pandas as pd
import numpy as np
from dataclasses import dataclass

from src.services.backtest.strategies.base import Signal


class TradingCalendar(Protocol):
    """交易日历接口（回测引擎内部使用）"""

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        """返回指定日期的下一个交易日"""
        ...

    def is_trading_day(self, date: pd.Timestamp) -> bool:
        """判断某日期是否为交易日"""
        ...


@dataclass(frozen=True)
class EquityCurvePoint:
    """权益曲线单点"""

    date: str
    strategy_value: float
    benchmark_value: float


@dataclass(frozen=True)
class TradeRecord:
    """单笔交易记录"""

    id: int
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float
    pnl_amount: float
    hold_days: int
    reason: str


@dataclass(frozen=True)
class EquityResult:
    """权益计算结果"""

    equity_curve: list[EquityCurvePoint]
    trades: list[TradeRecord]
    total_return: float
    max_drawdown: float
    win_rate: float
    avg_hold_days: float


class EquityCalculator:
    """权益计算器

    执行语义：
    1. 信号在 date 日收盘时生成
    2. 在 date 的**下一交易日**开盘价执行（通过 TradingCalendar 查找，非简单日期+1）
    3. 买入时按可用资金计算股数（向下取整）
    4. 卖出时扣除卖出费用

    仓位管理策略（单次持仓 one-position-at-a-time）：
    - 已有持仓时收到 buy 信号：忽略（不加仓）
    - 已有持仓时收到 sell 信号：平仓（按执行价卖出全部持仓）
    - 无持仓时收到 sell 信号：忽略（不空仓）
    - 同日内多个信号：仅处理第一个有效信号

    强制平仓：
    - 回测结束日（df 最后一条记录日期）若仍有持仓，按当日收盘价强制平仓
    - 强制平仓产生的交易计入 trades，reason 标注为 "force_close"

    基准曲线（买入并持有）：
    - 回测起始日按收盘价买入，持有至结束日
    - 期间不复权、不分红再投资
    - 每日 benchmark_value = 初始资金 × (当日收盘价 / 起始日收盘价)
    """

    FEE_RATES = {
        "cn": {"buy": 0.0003, "sell": 0.0013},
        "hk": {"buy": 0.0003, "sell": 0.0013},
        "us": {"buy": 0.0003, "sell": 0.0003},
    }
    INITIAL_CAPITAL = 100_000.0

    def __init__(
        self,
        calendar: TradingCalendar,
        market: Literal["cn", "hk", "us"] = "cn",
    ):
        rates = self.FEE_RATES.get(market, self.FEE_RATES["cn"])
        self._buy_fee_rate = rates["buy"]
        self._sell_fee_rate = rates["sell"]
        self._calendar = calendar
        self._market = market

    def calculate(self, df: pd.DataFrame, signals: list[Signal]) -> EquityResult:
        """计算权益曲线和交易记录

        TODO: 方法当前 140+ 行，核心循环和强制平仓逻辑可提取为独立方法
        以符合 <50 行函数的建议。留待重构阶段处理。
        """
        if df.empty:
            return self._empty_result()

        dates = df["date"].tolist()
        closes = df["close"].values

        # 构建日期 -> 行索引映射
        date_to_idx = {str(d): i for i, d in enumerate(dates)}

        # 基准曲线：买入并持有
        benchmark_value = self._calculate_benchmark(closes)

        # 无信号时返回初始资金曲线
        if not signals or all(s.action == "wait" for s in signals):
            equity_curve = [
                EquityCurvePoint(
                    date=str(dates[i]),
                    strategy_value=self.INITIAL_CAPITAL,
                    benchmark_value=benchmark_value[i],
                )
                for i in range(len(dates))
            ]
            return EquityResult(
                equity_curve=equity_curve,
                trades=[],
                total_return=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                avg_hold_days=0.0,
            )

        # 提取 buy/sell 信号
        action_signals = [s for s in signals if s.action in ("buy", "sell")]

        # 预先计算每个信号的执行日期（T+1），构建执行日→信号列表映射
        exec_date_to_signals: dict[str, list[Signal]] = {}
        for sig in action_signals:
            exec_date = self._get_execution_date(sig.date, date_to_idx, dates)
            # 若 T+1 超出数据范围，回退到信号生成日执行
            if exec_date is None or exec_date not in date_to_idx:
                exec_date = sig.date
            if exec_date in date_to_idx:
                exec_date_to_signals.setdefault(exec_date, []).append(sig)
            # TODO: 当信号日期和执行日期均不在 df 范围内时，信号被静默丢弃，应添加 logging.warning

        # 状态跟踪
        cash = self.INITIAL_CAPITAL
        shares = 0
        entry_price = 0.0
        entry_date = ""
        trades = []
        trade_id = 0

        # 逐日计算策略权益
        daily_strategy_value = []

        for i in range(len(dates)):
            current_date = str(dates[i])
            current_close = float(closes[i])

            # 处理今日待执行信号（仅第一个有效信号）
            pending_signals = exec_date_to_signals.get(current_date, [])
            for sig in pending_signals:
                exec_price = self._get_execution_price(sig, i, df)
                executed = False

                if sig.action == "buy" and shares == 0:
                    buy_cost = exec_price * (1 + self._buy_fee_rate)
                    max_shares = int(cash / buy_cost) if buy_cost > 0 else 0
                    if max_shares > 0:
                        shares = max_shares
                        entry_price = exec_price
                        entry_date = current_date
                        cash -= shares * exec_price * (1 + self._buy_fee_rate)
                        executed = True

                elif sig.action == "sell" and shares > 0:
                    sell_revenue = shares * exec_price * (1 - self._sell_fee_rate)
                    hold_days = self._days_between(entry_date, current_date)
                    return_pct = (exec_price - entry_price) / entry_price if entry_price > 0 else 0
                    pnl = sell_revenue - (shares * entry_price * (1 + self._buy_fee_rate))

                    trade_id += 1
                    trades.append(
                        TradeRecord(
                            id=trade_id,
                            entry_date=entry_date,
                            entry_price=entry_price,
                            exit_date=current_date,
                            exit_price=exec_price,
                            return_pct=return_pct,
                            pnl_amount=pnl,
                            hold_days=hold_days,
                            reason="signal",
                        )
                    )
                    cash += sell_revenue
                    shares = 0
                    entry_price = 0.0
                    entry_date = ""
                    executed = True

                if executed:
                    break

            # 计算当日策略权益
            strategy_value = cash + shares * current_close
            daily_strategy_value.append(strategy_value)

        # 强制平仓
        last_date = str(dates[-1])
        last_close = float(closes[-1])
        if shares > 0:
            sell_revenue = shares * last_close * (1 - self._sell_fee_rate)
            hold_days = self._days_between(entry_date, last_date)
            return_pct = (last_close - entry_price) / entry_price if entry_price > 0 else 0
            pnl = sell_revenue - (shares * entry_price * (1 + self._buy_fee_rate))

            trade_id += 1
            trades.append(
                TradeRecord(
                    id=trade_id,
                    entry_date=entry_date,
                    entry_price=entry_price,
                    exit_date=last_date,
                    exit_price=last_close,
                    return_pct=return_pct,
                    pnl_amount=pnl,
                    hold_days=hold_days,
                    reason="force_close",
                )
            )
            cash += sell_revenue
            shares = 0
            # 更新最后一天的策略权益
            daily_strategy_value[-1] = cash

        # 构建权益曲线
        equity_curve = [
            EquityCurvePoint(
                date=str(dates[i]),
                strategy_value=daily_strategy_value[i],
                benchmark_value=benchmark_value[i],
            )
            for i in range(len(dates))
        ]

        # 计算统计指标
        total_return = (daily_strategy_value[-1] - self.INITIAL_CAPITAL) / self.INITIAL_CAPITAL
        max_drawdown = self._calculate_max_drawdown(daily_strategy_value)
        win_rate = self._calculate_win_rate(trades)
        avg_hold_days = self._calculate_avg_hold_days(trades)

        return EquityResult(
            equity_curve=equity_curve,
            trades=trades,
            total_return=total_return,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            avg_hold_days=avg_hold_days,
        )

    def _get_execution_date(self, signal_date: str, date_to_idx: dict, dates: list) -> Optional[str]:
        """获取信号的执行日期（下一交易日）"""
        ts = pd.Timestamp(signal_date)
        exec_ts = self._calendar.next_trading_day(ts)
        return exec_ts.strftime("%Y-%m-%d")

    def _get_execution_price(self, sig: Signal, current_idx: int, df: pd.DataFrame) -> float:
        """获取执行价格"""
        # 优先使用信号中的 execution_price
        if sig.execution_price is not None:
            return sig.execution_price
        # 否则使用当日开盘价
        if "open" in df.columns and current_idx < len(df):
            return float(df["open"].iloc[current_idx])
        return float(df["close"].iloc[current_idx])

    def _calculate_benchmark(self, closes: np.ndarray) -> list[float]:
        """计算买入并持有基准曲线"""
        if len(closes) == 0 or closes[0] == 0:
            return [self.INITIAL_CAPITAL] * len(closes)
        first_close = float(closes[0])
        return [self.INITIAL_CAPITAL * (float(c) / first_close) for c in closes]

    def _calculate_max_drawdown(self, values: list[float]) -> float:
        """计算最大回撤"""
        if not values or values[0] == 0:
            return 0.0
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _calculate_win_rate(self, trades: list[TradeRecord]) -> float:
        """计算胜率"""
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.return_pct > 0)
        return wins / len(trades)

    def _calculate_avg_hold_days(self, trades: list[TradeRecord]) -> float:
        """计算平均持仓天数"""
        if not trades:
            return 0.0
        return sum(t.hold_days for t in trades) / len(trades)

    def _days_between(self, start: str, end: str) -> int:
        """计算两个日期之间的天数差"""
        try:
            start_dt = pd.Timestamp(start)
            end_dt = pd.Timestamp(end)
            return max(0, (end_dt - start_dt).days)
        except (ValueError, TypeError):
            return 0

    def _empty_result(self) -> EquityResult:
        """空数据返回初始资金结果"""
        return EquityResult(
            equity_curve=[],
            trades=[],
            total_return=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            avg_hold_days=0.0,
        )
