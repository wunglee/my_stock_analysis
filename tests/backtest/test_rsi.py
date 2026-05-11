"""测试 RSIStrategy（RSI 策略）"""

import pandas as pd

from src.services.backtest.strategies.rsi import RSIStrategy


class TestRSIConfig:
    """策略配置元数据测试"""

    def test_id(self):
        strategy = RSIStrategy()
        assert strategy.id == "rsi"

    def test_config(self):
        strategy = RSIStrategy()
        config = strategy.config
        assert config.id == "rsi"
        assert config.name == "RSI策略"
        assert config.category == "oscillator"
        assert len(config.parameters) == 3
        param_keys = {p.key for p in config.parameters}
        assert param_keys == {"period", "overbought", "oversold"}

    def test_min_warmup_bars(self):
        strategy = RSIStrategy()
        # period(14) + 2 = 16（信号比较需要两根连续有效 RSI）
        assert strategy.min_warmup_bars == 16

    def test_required_columns(self):
        strategy = RSIStrategy()
        assert strategy.required_columns == {"close"}


class TestRSIValidation:
    """参数校验测试"""

    def test_valid_params(self):
        strategy = RSIStrategy()
        errors = strategy.validate_params({"period": 14, "overbought": 70, "oversold": 30})
        assert errors == []

    def test_oversold_equals_overbought(self):
        strategy = RSIStrategy()
        errors = strategy.validate_params({"period": 14, "overbought": 50, "oversold": 50})
        assert len(errors) == 1

    def test_oversold_greater_than_overbought(self):
        strategy = RSIStrategy()
        # oversold=65 超出 max=50 触发范围错误，同时 oversold > overbought 触发跨参数错误
        errors = strategy.validate_params({"period": 14, "overbought": 60, "oversold": 65})
        assert len(errors) == 2

    def test_missing_params_use_defaults(self):
        strategy = RSIStrategy()
        errors = strategy.validate_params({})
        assert errors == []


class TestRSISignals:
    """信号生成测试"""

    def _make_df(self, prices: list[float], dates: list[str] | None = None) -> pd.DataFrame:
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

    def test_oversold_buy(self):
        """RSI 从超卖区回升 → buy"""
        # 持续下跌使 RSI 降到超卖区，然后反弹
        prices = [100.0] * 15 + [98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0] + [94.0, 96.0, 98.0, 100.0, 102.0]
        df = self._make_df(prices)
        strategy = RSIStrategy()
        signals = strategy.generate_signals(df, {"period": 14, "overbought": 70, "oversold": 30})

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1

    def test_overbought_sell(self):
        """RSI 从超买区回落 → sell"""
        # 持续上涨使 RSI 升到超买区，然后回落
        prices = [100.0] * 15 + [102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0] + [112.0, 110.0, 108.0, 106.0, 104.0]
        df = self._make_df(prices)
        strategy = RSIStrategy()
        signals = strategy.generate_signals(df, {"period": 14, "overbought": 70, "oversold": 30})

        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1

    def test_stable_prices_no_signal(self):
        """稳定价格时 RSI 在正常区域，不应产生信号"""
        prices = [100.0] * 50  # 完全横盘
        df = self._make_df(prices)
        strategy = RSIStrategy()
        signals = strategy.generate_signals(df, {"period": 14, "overbought": 70, "oversold": 30})

        non_wait = [s for s in signals if s.action != "wait"]
        assert len(non_wait) == 0

    def test_signal_has_reason(self):
        """信号包含触发理由"""
        prices = [100.0] * 15 + [98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0] + [94.0, 96.0, 98.0, 100.0, 102.0]
        df = self._make_df(prices)
        strategy = RSIStrategy()
        signals = strategy.generate_signals(df, {"period": 14, "overbought": 70, "oversold": 30})

        buy_signals = [s for s in signals if s.action == "buy"]
        if buy_signals:
            assert len(buy_signals[0].reasons) > 0

    def test_insufficient_data(self):
        """数据不足时返回空列表"""
        prices = [100.0] * 10  # 不够 warmup=16
        df = self._make_df(prices)
        strategy = RSIStrategy()
        signals = strategy.generate_signals(df, {"period": 14, "overbought": 70, "oversold": 30})
        assert signals == []

    def test_custom_thresholds(self):
        """自定义超买超卖阈值应影响信号产生"""
        prices = [100.0] * 20 + [98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0]
        df = self._make_df(prices)
        strategy = RSIStrategy()
        # 宽松阈值：难触发（80/20）
        signals_loose = strategy.generate_signals(df, {"period": 14, "overbought": 80, "oversold": 20})
        # 严格阈值：易触发（60/40）
        signals_tight = strategy.generate_signals(df, {"period": 14, "overbought": 60, "oversold": 40})
        buy_tight = len([s for s in signals_tight if s.action == "buy"])
        buy_loose = len([s for s in signals_loose if s.action == "buy"])
        # 更严格的阈值应产生更多买入信号
        assert buy_tight >= buy_loose

    def test_signal_entry_price_is_close(self):
        """信号的 entry_price 为当日收盘价"""
        prices = [100.0] * 15 + [98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0] + [94.0, 96.0, 98.0, 100.0, 102.0]
        df = self._make_df(prices)
        strategy = RSIStrategy()
        signals = strategy.generate_signals(df, {"period": 14, "overbought": 70, "oversold": 30})

        buy_signals = [s for s in signals if s.action == "buy"]
        if buy_signals:
            row = df[df["date"] == buy_signals[0].date].iloc[0]
            assert buy_signals[0].entry_price == row["close"]
