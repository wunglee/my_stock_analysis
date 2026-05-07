"""纯技术回测服务

基于真实 K 线数据计算技术指标，生成交易信号并回测验证。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data_provider.base import DataFetcherManager
from src.chart_legacy.timeseries_calculator import TimeSeriesCalculator

logger = logging.getLogger(__name__)


@dataclass
class TechnicalSignal:
    date: str
    action: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    reasons: List[str]
    confidence: float


@dataclass
class TechnicalEvaluation:
    signal_date: str
    action: str
    outcome: str
    stock_return_pct: float
    hit_take_profit: bool
    hit_stop_loss: bool
    direction_correct: bool


@dataclass
class TechnicalRule:
    name: str
    condition: str
    sample_count: int
    win_rate: float
    avg_return_5d: float
    confidence: float


@dataclass
class StockBacktestResult:
    code: str
    stock_name: str
    date_range: str
    total_signals: int
    win_rate: float
    avg_return: float
    max_drawdown: float
    kline_data: List[dict]
    rules: List[TechnicalRule]
    signals: List[TechnicalSignal]
    evaluations: List[TechnicalEvaluation]


class TechnicalBacktestService:
    """纯技术回测服务"""

    # 信号评估参数
    TAKE_PROFIT_PCT = 0.03
    STOP_LOSS_PCT = -0.03

    def __init__(self):
        self._fetcher = DataFetcherManager()
        self._calc = TimeSeriesCalculator()

    def run_backtest(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        eval_window_days: int = 10,
    ) -> Dict:
        """运行纯技术回测

        Args:
            codes: 股票代码列表
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            eval_window_days: 评估窗口天数

        Returns:
            符合 TechnicalBacktestResult 结构的结果字典
        """
        per_stock: Dict[str, StockBacktestResult] = {}
        price_series: Dict[str, pd.Series] = {}

        for code in codes:
            try:
                result = self._analyze_single_stock(
                    code, start_date, end_date, eval_window_days
                )
                per_stock[code] = result
                if result.kline_data:
                    closes = [d["close"] for d in result.kline_data]
                    price_series[code] = pd.Series(closes)
            except Exception as e:
                logger.error(f"[{code}] 技术回测失败: {e}", exc_info=True)

        # 跨股票相关性
        correlations = []
        codes_list = list(price_series.keys())
        for i in range(len(codes_list)):
            for j in range(i + 1, len(codes_list)):
                c1, c2 = codes_list[i], codes_list[j]
                min_len = min(len(price_series[c1]), len(price_series[c2]))
                if min_len > 10:
                    corr = price_series[c1].iloc[:min_len].corr(
                        price_series[c2].iloc[:min_len]
                    )
                    if not pd.isna(corr):
                        correlations.append({
                            "code_a": c1,
                            "code_b": c2,
                            "price_correlation": round(float(corr), 2),
                        })

        return {
            "meta": {
                "mode": "technical",
                "codes": codes,
                "date_range": [start_date, end_date],
                "eval_window_days": eval_window_days,
                "generated_at": pd.Timestamp.now().isoformat(),
            },
            "per_stock": {
                code: {
                    "code": r.code,
                    "stock_name": r.stock_name,
                    "date_range": r.date_range,
                    "total_signals": r.total_signals,
                    "win_rate": r.win_rate,
                    "avg_return": r.avg_return,
                    "max_drawdown": r.max_drawdown,
                    "kline_data": r.kline_data,
                    "rules": [
                        {
                            "name": rule.name,
                            "condition": rule.condition,
                            "sample_count": rule.sample_count,
                            "win_rate": rule.win_rate,
                            "avg_return_5d": rule.avg_return_5d,
                            "confidence": rule.confidence,
                        }
                        for rule in r.rules
                    ],
                    "signals": [
                        {
                            "date": s.date,
                            "action": s.action,
                            "entry_price": s.entry_price,
                            "stop_loss": s.stop_loss,
                            "take_profit": s.take_profit,
                            "reasons": s.reasons,
                            "confidence": s.confidence,
                        }
                        for s in r.signals
                    ],
                    "evaluations": [
                        {
                            "signal_date": e.signal_date,
                            "action": e.action,
                            "outcome": e.outcome,
                            "stock_return_pct": e.stock_return_pct,
                            "hit_take_profit": e.hit_take_profit,
                            "hit_stop_loss": e.hit_stop_loss,
                            "direction_correct": e.direction_correct,
                        }
                        for e in r.evaluations
                    ],
                }
                for code, r in per_stock.items()
            },
            "cross_stock": {"correlations": correlations},
        }

    def _analyze_single_stock(
        self,
        code: str,
        start_date: str,
        end_date: str,
        eval_window_days: int,
    ) -> StockBacktestResult:
        """分析单只股票"""
        # 1. 获取数据
        df, _ = self._fetcher.get_daily_data(
            stock_code=code,
            start_date=start_date,
            end_date=end_date,
        )
        if df is None or df.empty:
            raise ValueError(f"{code} 无数据")

        # 标准化列名
        df = df.copy()
        if "trade_date" in df.columns:
            df["date"] = pd.to_datetime(df["trade_date"])
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            df["date"] = pd.to_datetime(df.index)

        df = df.sort_values("date").reset_index(drop=True)

        # 2. 计算技术指标
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        ma5 = self._calc.calculate_sma(close, 5)
        ma10 = self._calc.calculate_sma(close, 10)
        ma20 = self._calc.calculate_sma(close, 20)

        # MACD
        macd_main, macd_signal, macd_hist = self._calc.calculate_dual_ema_oscillator(
            close, 12, 26, 9
        )

        # RSI
        rsi = self._calc.calculate_momentum_index(close, 14)

        # KDJ (简化: 只用 RSV 和 K)
        rsv, k_smooth = self._calc.calculate_range_position(high, low, close, 9, 3)

        # 成交量指标
        vol_ma5 = volume.rolling(5).mean()
        vol_ratio = volume / vol_ma5.replace(0, np.nan)

        # 前高（20日）
        high_20 = high.rolling(20).max().shift(1)

        # 组装指标 DataFrame
        ind = pd.DataFrame(
            {
                "date": df["date"],
                "open": df["open"],
                "high": df["high"],
                "low": df["low"],
                "close": df["close"],
                "volume": df["volume"],
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
                "macd_hist": macd_hist,
                "rsi": rsi,
                "k": k_smooth,
                "vol_ratio": vol_ratio,
                "high_20": high_20,
            }
        )

        # 3. 生成交易信号
        signals = self._generate_signals(ind)

        # 4. 回测验证
        evaluations = self._evaluate_signals(ind, signals, eval_window_days)

        # 5. 统计规律（规则绩效）
        rules = self._summarize_rules(signals, evaluations)

        # 6. 计算整体指标
        total_signals = len(signals)
        win_count = sum(1 for e in evaluations if e.outcome == "win")
        win_rate = win_count / total_signals if total_signals > 0 else 0
        avg_return = (
            np.mean([e.stock_return_pct for e in evaluations]) if evaluations else 0
        )
        max_dd = self._calculate_max_drawdown(close)

        # 7. K 线数据（用于前端图表）
        kline_data = []
        for _, row in df.iterrows():
            kline_data.append(
                {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "volume": int(row["volume"]),
                }
            )

        # 获取股票名称
        stock_name = self._fetcher.get_stock_name(code) or code

        date_range_str = f"{df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}"

        return StockBacktestResult(
            code=code,
            stock_name=stock_name,
            date_range=date_range_str,
            total_signals=total_signals,
            win_rate=round(win_rate, 2),
            avg_return=round(avg_return, 2),
            max_drawdown=round(max_dd, 2),
            kline_data=kline_data,
            rules=rules,
            signals=signals,
            evaluations=evaluations,
        )

    def _generate_signals(self, ind: pd.DataFrame) -> List[TechnicalSignal]:
        """基于技术指标生成交易信号"""
        signals: List[TechnicalSignal] = []

        # 需要足够的预热数据
        valid_start = 25

        for i in range(valid_start, len(ind)):
            row = ind.iloc[i]
            prev = ind.iloc[i - 1]

            date_str = row["date"].strftime("%Y-%m-%d")
            close_p = float(row["close"])
            reasons: List[str] = []
            action = "wait"
            confidence = 0.5
            entry_price: Optional[float] = None
            stop_loss: Optional[float] = None
            take_profit: Optional[float] = None

            # 规则1: MA20 支撑 — 价格触及 MA20±0.5%
            if pd.notna(row["ma20"]):
                ma20 = float(row["ma20"])
                dist_to_ma20 = abs(close_p - ma20) / ma20
                if dist_to_ma20 <= 0.005 and close_p >= ma20:
                    action = "buy"
                    reasons.append("MA20支撑")
                    confidence = 0.75
                    entry_price = close_p
                    stop_loss = round(ma20 * 0.97, 2)
                    take_profit = round(close_p * 1.06, 2)

            # 规则2: 缩量回调 — 量比<0.8 且价格回踩 MA5
            if (
                action == "wait"
                and pd.notna(row["vol_ratio"])
                and pd.notna(row["ma5"])
            ):
                vol_r = float(row["vol_ratio"])
                ma5 = float(row["ma5"])
                if vol_r < 0.8 and abs(close_p - ma5) / ma5 <= 0.01 and close_p <= ma5:
                    action = "buy"
                    reasons.append("缩量回调")
                    confidence = 0.78
                    entry_price = close_p
                    stop_loss = round(ma5 * 0.96, 2)
                    take_profit = round(close_p * 1.05, 2)

            # 规则3: 放量突破 — 量比>2 且价格突破前高
            if (
                action == "wait"
                and pd.notna(row["vol_ratio"])
                and pd.notna(row["high_20"])
            ):
                vol_r = float(row["vol_ratio"])
                h20 = float(row["high_20"])
                if vol_r > 2.0 and close_p > h20 * 1.01:
                    action = "buy"
                    reasons.append("放量突破")
                    confidence = 0.65
                    entry_price = close_p
                    stop_loss = round(h20 * 0.98, 2)
                    take_profit = round(close_p * 1.08, 2)

            # 规则4: 金叉买入 — MA5 上穿 MA10
            if action == "wait" and pd.notna(row["ma5"]) and pd.notna(row["ma10"]):
                ma5 = float(row["ma5"])
                ma10 = float(row["ma10"])
                prev_ma5 = float(prev["ma5"]) if pd.notna(prev["ma5"]) else None
                prev_ma10 = float(prev["ma10"]) if pd.notna(prev["ma10"]) else None
                if (
                    prev_ma5 is not None
                    and prev_ma10 is not None
                    and prev_ma5 <= prev_ma10
                    and ma5 > ma10
                ):
                    action = "buy"
                    reasons.append("金叉买入")
                    confidence = 0.70
                    entry_price = close_p
                    stop_loss = round(ma10 * 0.96, 2)
                    take_profit = round(close_p * 1.06, 2)

            # 规则5: 死叉卖出 / 跌破 MA20
            if action == "wait" and pd.notna(row["ma5"]) and pd.notna(row["ma10"]):
                ma5 = float(row["ma5"])
                ma10 = float(row["ma10"])
                prev_ma5 = float(prev["ma5"]) if pd.notna(prev["ma5"]) else None
                prev_ma10 = float(prev["ma10"]) if pd.notna(prev["ma10"]) else None
                if (
                    prev_ma5 is not None
                    and prev_ma10 is not None
                    and prev_ma5 >= prev_ma10
                    and ma5 < ma10
                ):
                    action = "sell"
                    reasons.append("死叉卖出")
                    confidence = 0.72

            # 规则6: RSI 超卖反弹
            if action == "wait" and pd.notna(row["rsi"]):
                rsi_val = float(row["rsi"])
                if rsi_val < 30:
                    action = "buy"
                    reasons.append("RSI超卖")
                    confidence = 0.60
                    entry_price = close_p
                    stop_loss = round(close_p * 0.95, 2)
                    take_profit = round(close_p * 1.04, 2)

            if reasons:
                signals.append(
                    TechnicalSignal(
                        date=date_str,
                        action=action,
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        reasons=reasons,
                        confidence=round(confidence, 2),
                    )
                )

        return signals

    def _evaluate_signals(
        self,
        ind: pd.DataFrame,
        signals: List[TechnicalSignal],
        eval_window_days: int,
    ) -> List[TechnicalEvaluation]:
        """回测验证信号表现"""
        evaluations: List[TechnicalEvaluation] = []
        close_series = ind["close"].values

        for sig in signals:
            # 找到信号日在数据中的位置
            mask = ind["date"].dt.strftime("%Y-%m-%d") == sig.date
            if not mask.any():
                continue
            idx = mask.idxmax()

            # 计算 eval_window_days 后的收益
            future_idx = idx + eval_window_days
            if future_idx >= len(ind):
                future_idx = len(ind) - 1

            entry_price = sig.entry_price or float(ind.iloc[idx]["close"])
            future_price = float(ind.iloc[future_idx]["close"])
            return_pct = (future_price - entry_price) / entry_price * 100

            # 同时检查期间是否触及止损/止盈
            period_low = float(ind.iloc[idx:future_idx]["low"].min())
            period_high = float(ind.iloc[idx:future_idx]["high"].max())

            hit_sl = False
            hit_tp = False

            if sig.stop_loss is not None and period_low <= sig.stop_loss:
                hit_sl = True
            if sig.take_profit is not None and period_high >= sig.take_profit:
                hit_tp = True

            # 判定结果
            if sig.action == "buy":
                if return_pct >= 3.0 or hit_tp:
                    outcome = "win"
                elif return_pct <= -3.0 or hit_sl:
                    outcome = "loss"
                else:
                    outcome = "neutral"
                direction_correct = future_price >= entry_price
            elif sig.action == "sell":
                if return_pct <= -3.0:
                    outcome = "win"
                elif return_pct >= 3.0:
                    outcome = "loss"
                else:
                    outcome = "neutral"
                direction_correct = future_price <= entry_price
            else:
                outcome = "neutral"
                direction_correct = abs(return_pct) < 1.0

            evaluations.append(
                TechnicalEvaluation(
                    signal_date=sig.date,
                    action=sig.action,
                    outcome=outcome,
                    stock_return_pct=round(return_pct, 2),
                    hit_take_profit=hit_tp,
                    hit_stop_loss=hit_sl,
                    direction_correct=direction_correct,
                )
            )

        return evaluations

    def _summarize_rules(
        self,
        signals: List[TechnicalSignal],
        evaluations: List[TechnicalEvaluation],
    ) -> List[TechnicalRule]:
        """统计各规则的胜率"""
        rule_stats: Dict[str, dict] = {}

        for sig, ev in zip(signals, evaluations):
            for reason in sig.reasons:
                if reason not in rule_stats:
                    rule_stats[reason] = {
                        "count": 0,
                        "wins": 0,
                        "returns": [],
                    }
                rule_stats[reason]["count"] += 1
                if ev.outcome == "win":
                    rule_stats[reason]["wins"] += 1
                rule_stats[reason]["returns"].append(ev.stock_return_pct)

        rule_conditions = {
            "MA20支撑": "价格触及MA20±0.5%",
            "缩量回调": "量比<0.8且价格回踩MA5",
            "放量突破": "量比>2且价格突破前高",
            "金叉买入": "MA5上穿MA10",
            "死叉卖出": "MA5下穿MA10",
            "RSI超卖": "RSI<30后反弹",
        }

        rules: List[TechnicalRule] = []
        for name, stats in sorted(
            rule_stats.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            count = stats["count"]
            wins = stats["wins"]
            returns = stats["returns"]
            rules.append(
                TechnicalRule(
                    name=name,
                    condition=rule_conditions.get(name, ""),
                    sample_count=count,
                    win_rate=round(wins / count, 2) if count > 0 else 0,
                    avg_return_5d=round(np.mean(returns), 2) if returns else 0,
                    confidence=round(0.6 + 0.2 * (wins / count if count > 0 else 0), 2),
                )
            )

        return rules

    def _calculate_max_drawdown(self, prices: pd.Series) -> float:
        """计算最大回撤"""
        if len(prices) < 2:
            return 0.0
        cumulative_max = prices.cummax()
        drawdown = (prices - cumulative_max) / cumulative_max
        return float(drawdown.min() * 100)
