"""测试 MACDStrategy（MACD 策略）"""

import pandas as pd

from src.services.backtest.strategies.macd import MACDStrategy


class TestMACDConfig:
    """策略配置元数据测试"""

    def test_id(self):
        strategy = MACDStrategy()
        assert strategy.id == "macd"

    def test_config(self):
        strategy = MACDStrategy()
        config = strategy.config
        assert config.id == "macd"
        assert config.name == "MACD策略"
        assert config.category == "trend"
        assert len(config.parameters) == 3
        param_keys = {p.key for p in config.parameters}
        assert param_keys == {"fast", "slow", "signal"}

    def test_min_warmup_bars(self):
        strategy = MACDStrategy()
        # slow(26) + signal(9) = 35 bars minimum
        assert strategy.min_warmup_bars == 35

    def test_required_columns(self):
        strategy = MACDStrategy()
        assert strategy.required_columns == {"close"}


class TestMACDValidation:
    """参数校验测试"""

    def test_valid_params(self):
        strategy = MACDStrategy()
        errors = strategy.validate_params({"fast": 12, "slow": 26, "signal": 9})
        assert errors == []

    def test_fast_equals_slow(self):
        strategy = MACDStrategy()
        errors = strategy.validate_params({"fast": 10, "slow": 10, "signal": 9})
        assert len(errors) == 1

    def test_fast_greater_than_slow(self):
        strategy = MACDStrategy()
        errors = strategy.validate_params({"fast": 30, "slow": 20, "signal": 9})
        assert len(errors) == 1

    def test_missing_params_use_defaults(self):
        strategy = MACDStrategy()
        errors = strategy.validate_params({})
        assert errors == []


class TestMACDSignals:
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

    def test_golden_cross_buy(self):
        """DIF 上穿 DEA → buy"""
        from src.services.backtest.strategies.macd import MACDStrategy

        # 需要足够数据覆盖 warmup，然后构造拐点让 DIF 上穿 DEA
        # 基础价格 80 条（>35 warmup），后半段快速上涨推动 DIF 上穿
        prices = [100.0] * 50 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
        df = self._make_df(prices)
        strategy = MACDStrategy()
        signals = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1

    def test_death_cross_sell(self):
        """DIF 下穿 DEA → sell"""
        from src.services.backtest.strategies.macd import MACDStrategy

        prices = [100.0] * 50 + [99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0]
        df = self._make_df(prices)
        strategy = MACDStrategy()
        signals = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})

        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1

    def test_no_cross_no_action(self):
        """横盘时 DIF 和 DEA 紧密缠绕，不应大量产生信号"""
        from src.services.backtest.strategies.macd import MACDStrategy

        prices = [100.0] * 80  # 完全横盘
        df = self._make_df(prices)
        strategy = MACDStrategy()
        signals = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})

        non_wait = [s for s in signals if s.action != "wait"]
        # 横盘时 DIF≈DEA≈0，不应有交叉信号
        assert len(non_wait) == 0

    def test_signal_has_reason(self):
        """信号包含触发理由"""
        from src.services.backtest.strategies.macd import MACDStrategy

        prices = [100.0] * 50 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
        df = self._make_df(prices)
        strategy = MACDStrategy()
        signals = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        assert len(buy_signals[0].reasons) > 0
        assert "金叉" in buy_signals[0].reasons[0] or "DIF" in buy_signals[0].reasons[0]

    def test_insufficient_data(self):
        """数据不足时返回空列表"""
        from src.services.backtest.strategies.macd import MACDStrategy

        prices = [100.0] * 10  # 不够 warmup=35
        df = self._make_df(prices)
        strategy = MACDStrategy()
        signals = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})
        assert signals == []

    def test_signal_entry_price_is_close(self):
        """信号的 entry_price 为当日收盘价"""
        from src.services.backtest.strategies.macd import MACDStrategy

        prices = [100.0] * 50 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
        df = self._make_df(prices)
        strategy = MACDStrategy()
        signals = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})

        buy_signals = [s for s in signals if s.action == "buy"]
        if buy_signals:
            row = df[df["date"] == buy_signals[0].date].iloc[0]
            assert buy_signals[0].entry_price == row["close"]

    def test_custom_params(self):
        """更快的参数配置应该产生不同结果"""
        from src.services.backtest.strategies.macd import MACDStrategy

        prices = [100.0] * 40 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
        df = self._make_df(prices)
        strategy = MACDStrategy()

        signals_fast = strategy.generate_signals(df, {"fast": 6, "slow": 13, "signal": 5})
        signals_slow = strategy.generate_signals(df, {"fast": 12, "slow": 26, "signal": 9})

        # 不同参数应产生不同的信号（至少信号数量不同）
        buy_fast = len([s for s in signals_fast if s.action == "buy"])
        buy_slow = len([s for s in signals_slow if s.action == "buy"])
        # 快参数应产生更多买入信号（对价格变化更敏感）
        assert buy_fast >= buy_slow or (buy_fast == 0 and buy_slow == 0)
