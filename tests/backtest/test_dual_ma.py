"""测试 DualMAStrategy（双均线策略）"""

import pandas as pd
import pytest

from src.services.backtest.strategies.base import Signal
from src.services.backtest.strategies.dual_ma import DualMAStrategy


class TestDualMAConfig:
    """策略配置元数据测试"""

    def test_id(self):
        strategy = DualMAStrategy()
        assert strategy.id == "dual_ma"

    def test_config(self):
        strategy = DualMAStrategy()
        config = strategy.config
        assert config.id == "dual_ma"
        assert config.name == "双均线策略"
        assert config.category == "trend"
        assert len(config.parameters) == 2

    def test_min_warmup_bars(self):
        strategy = DualMAStrategy()
        # warmup bars 应等于最长均线周期
        assert strategy.min_warmup_bars == 20  # default long_period

    def test_required_columns(self):
        strategy = DualMAStrategy()
        assert strategy.required_columns == {"close"}


class TestDualMAValidation:
    """参数校验测试"""

    def test_valid_params(self):
        strategy = DualMAStrategy()
        errors = strategy.validate_params({"short_period": 5, "long_period": 20})
        assert errors == []

    def test_short_equal_long(self):
        strategy = DualMAStrategy()
        errors = strategy.validate_params({"short_period": 10, "long_period": 10})
        assert len(errors) == 1
        assert "短期周期必须小于长期周期" in errors[0]

    def test_short_greater_than_long(self):
        strategy = DualMAStrategy()
        errors = strategy.validate_params({"short_period": 30, "long_period": 20})
        assert len(errors) == 1

    def test_missing_param(self):
        strategy = DualMAStrategy()
        # 缺失参数时使用默认值，校验通过
        errors = strategy.validate_params({})
        assert errors == []


class TestDualMASignals:
    """信号生成测试"""

    def _make_df(self, prices: list[float], dates: list[str] | None = None) -> pd.DataFrame:
        """辅助方法：构造价格序列 DataFrame"""
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def test_golden_cross_buy(self):
        """金叉：短期均线上穿长期均线 → buy"""
        # 构造价格序列：前20日低价横盘，后5日快速上涨形成金叉
        prices = [100.0] * 20 + [101.0, 102.0, 103.0, 104.0, 105.0]
        df = self._make_df(prices)
        strategy = DualMAStrategy()
        signals = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})

        # 寻找 buy 信号
        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        # 金叉应在价格开始上涨后出现
        assert buy_signals[0].date >= "2024-01-21"

    def test_death_cross_sell(self):
        """死叉：短期均线下穿长期均线 → sell"""
        # 构造价格序列：前20日高价横盘，后5日快速下跌形成死叉
        prices = [100.0] * 20 + [99.0, 98.0, 97.0, 96.0, 95.0]
        df = self._make_df(prices)
        strategy = DualMAStrategy()
        signals = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})

        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1
        assert sell_signals[0].date >= "2024-01-21"

    def test_no_cross_wait(self):
        """无交叉时全为 wait"""
        prices = [100.0] * 30  # 完全横盘，均线无交叉
        df = self._make_df(prices)
        strategy = DualMAStrategy()
        signals = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})

        non_wait = [s for s in signals if s.action != "wait"]
        assert len(non_wait) == 0

    def test_custom_params(self):
        """自定义参数生效"""
        prices = [100.0] * 15 + [110.0] * 10  # 15日低价后跳涨
        df = self._make_df(prices)
        strategy = DualMAStrategy()

        # short=3, long=5 应该比 short=5, long=10 更早出现金叉
        signals_fast = strategy.generate_signals(df, {"short_period": 3, "long_period": 5})
        signals_slow = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})

        buy_fast = [s for s in signals_fast if s.action == "buy"]
        buy_slow = [s for s in signals_slow if s.action == "buy"]

        assert len(buy_fast) >= 1
        assert len(buy_slow) >= 1
        # 快参数的信号应比慢参数更早出现（或至少不晚）
        assert buy_fast[0].date <= buy_slow[0].date

    def test_signal_has_reason(self):
        """信号包含触发理由"""
        prices = [100.0] * 20 + [101.0, 102.0, 103.0, 104.0, 105.0]
        df = self._make_df(prices)
        strategy = DualMAStrategy()
        signals = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        assert len(buy_signals[0].reasons) > 0
        assert "金叉" in buy_signals[0].reasons[0] or "均线上穿" in buy_signals[0].reasons[0]

    def test_signal_entry_price(self):
        """信号的 entry_price 为当日收盘价"""
        prices = [100.0] * 20 + [101.0, 102.0, 103.0, 104.0, 105.0]
        df = self._make_df(prices)
        strategy = DualMAStrategy()
        signals = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        # entry_price 应为当日收盘价
        row = df[df["date"] == buy_signals[0].date].iloc[0]
        assert buy_signals[0].entry_price == row["close"]

    def test_insufficient_data(self):
        """数据不足时应返回空列表（不报错，由 SignalGenerator 负责校验长度）"""
        prices = [100.0] * 5  # 只有5条，不够 long_period=10
        df = self._make_df(prices)
        strategy = DualMAStrategy()
        signals = strategy.generate_signals(df, {"short_period": 5, "long_period": 10})
        # 策略内部应优雅处理，返回空列表
        assert signals == []
