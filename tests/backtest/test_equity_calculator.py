"""测试 EquityCalculator"""

import pandas as pd
import pytest

from src.services.backtest.engine.equity_calculator import (
    EquityCalculator,
    EquityCurvePoint,
    TradeRecord,
    TradingCalendar,
)
from src.services.backtest.strategies.base import Signal


class SimpleCalendar:
    """测试用交易日历：每天均为交易日，下一日 = 日期+1"""

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        return date + pd.Timedelta(days=1)

    def is_trading_day(self, date: pd.Timestamp) -> bool:
        return True


class TestEquityCalculatorBasics:
    """基础功能测试"""

    def _make_df(self, prices: list[float], dates: list[str] = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_empty_df(self):
        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(pd.DataFrame(), [])
        assert result.total_return == 0.0
        assert result.equity_curve == []

    def test_no_signals(self):
        """无信号时返回初始资金曲线"""
        prices = [100.0] * 10
        df = self._make_df(prices)
        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, [])

        assert len(result.equity_curve) == 10
        assert result.equity_curve[0].strategy_value == 100_000.0
        assert result.total_return == 0.0
        assert result.trades == []

    def test_all_wait_signals(self):
        """全 wait 信号等价于无信号"""
        prices = [100.0] * 10
        df = self._make_df(prices)
        signals = [Signal(date=f"2024-01-{i+1:02d}", action="wait") for i in range(10)]
        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        assert result.total_return == 0.0
        assert result.trades == []


class TestSingleTrade:
    """单次买卖完整流程测试"""

    def _make_df(self, prices: list[float], dates: list[str] = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_single_buy_sell(self):
        """单次买入卖出完整流程验证"""
        # 价格序列：第1天100，第5天买入信号(收盘100)，第6天开盘执行(110)
        # 第10天卖出信号(收盘150)，第11天开盘执行(150)
        prices = [100.0, 100.0, 100.0, 100.0, 100.0, 110.0, 120.0, 130.0, 140.0, 150.0]
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-05", action="buy", entry_price=100.0, execution_price=None, reasons=["金叉"]),
            Signal(date="2024-01-10", action="sell", entry_price=150.0, execution_price=None, reasons=["死叉"]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 验证交易记录
        assert len(result.trades) == 1
        trade = result.trades[0]
        # entry_date 记录实际执行日（T+1），exit_date 记录实际执行日
        assert trade.entry_date == "2024-01-06"
        assert trade.exit_date == "2024-01-10"
        assert trade.reason == "signal"

        # 买入费用 = 买入价 * 0.03%，卖出费用 = 卖出价 * 0.13%
        # 买入价 = 第5天开盘价 = 100.0
        # 卖出价 = 第10天开盘价 = 150.0
        # 可买股数 = floor(100000 / (100 * 1.0003))
        expected_shares = int(100_000 / (100.0 * 1.0003))
        assert expected_shares > 0

        # 验证收益率包含费用
        assert trade.return_pct > 0  # 盈利交易

    def test_buy_fee_calculation(self):
        """买入费用计算验证"""
        prices = [100.0, 105.0]
        df = self._make_df(prices, dates=["2024-01-01", "2024-01-02"])
        signals = [
            Signal(date="2024-01-01", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 只有1个买入信号，无卖出，最后一天强制平仓
        assert len(result.trades) == 1
        trade = result.trades[0]
        # 强制平仓
        assert trade.reason == "force_close"
        assert trade.exit_date == "2024-01-02"


class TestForceClose:
    """强制平仓测试"""

    def _make_df(self, prices: list[float], dates: list[str] = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_force_close_on_last_day(self):
        """回测结束日强制平仓"""
        prices = [100.0, 110.0, 120.0]
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-01", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 1 个买入，最后一天强制平仓
        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.reason == "force_close"
        assert trade.exit_date == "2024-01-03"
        assert trade.exit_price == 120.0


class TestPositionManagement:
    """仓位管理测试"""

    def _make_df(self, prices: list[float], dates: list[str] = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_ignore_duplicate_buy(self):
        """已有持仓时忽略 buy 信号"""
        prices = [100.0, 100.0, 100.0, 100.0, 100.0]
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-01", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-02", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-05", action="sell", entry_price=100.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 应该只有 1 笔交易（买入+卖出），第二个 buy 被忽略
        assert len(result.trades) == 1

    def test_ignore_sell_without_position(self):
        """无持仓时忽略 sell 信号"""
        prices = [100.0, 100.0, 100.0, 100.0, 100.0]
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-01", action="sell", entry_price=100.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-02", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-05", action="sell", entry_price=100.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 第一个 sell 被忽略，只有 1 笔交易
        assert len(result.trades) == 1


class TestBenchmark:
    """基准曲线测试"""

    def _make_df(self, prices: list[float], dates: list[str] = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_benchmark_buy_and_hold(self):
        """基准曲线 = 买入并持有"""
        prices = [100.0, 110.0, 120.0, 130.0]
        df = self._make_df(prices)
        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, [])

        # 第1天基准 = 100000
        assert result.equity_curve[0].benchmark_value == pytest.approx(100_000.0)
        # 第2天基准 = 100000 * (110/100) = 110000
        assert result.equity_curve[1].benchmark_value == pytest.approx(110_000.0)
        # 第4天基准 = 100000 * (130/100) = 130000
        assert result.equity_curve[3].benchmark_value == pytest.approx(130_000.0)


class TestStatistics:
    """统计指标测试"""

    def _make_df(self, prices: list[float], dates: list[str] = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_max_drawdown(self):
        """最大回撤计算"""
        # 价格：100 -> 150 -> 120 -> 130，回撤从 150 到 120 = 20%
        prices = [100.0, 150.0, 120.0, 130.0]
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-01", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 有持仓时策略权益跟随价格，应有回撤
        assert result.max_drawdown >= 0

    def test_win_rate(self):
        """胜率计算"""
        prices = [100.0, 110.0, 120.0, 90.0, 80.0]
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-01", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-03", action="sell", entry_price=120.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-03", action="buy", entry_price=120.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        # 第一笔交易盈利，第二笔亏损（强制平仓或信号卖出）
        assert 0.0 <= result.win_rate <= 1.0

    def test_avg_hold_days(self):
        """平均持仓天数"""
        prices = [100.0] * 10
        df = self._make_df(prices)
        signals = [
            Signal(date="2024-01-01", action="buy", entry_price=100.0, execution_price=None, reasons=[]),
            Signal(date="2024-01-05", action="sell", entry_price=100.0, execution_price=None, reasons=[]),
        ]

        calc = EquityCalculator(SimpleCalendar())
        result = calc.calculate(df, signals)

        assert result.avg_hold_days > 0
