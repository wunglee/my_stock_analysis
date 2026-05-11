"""测试 BollingerStrategy（布林带策略）"""

import pandas as pd

from src.services.backtest.strategies.bollinger import BollingerStrategy


class TestBollingerConfig:
    """策略配置元数据测试"""

    def test_id(self):
        strategy = BollingerStrategy()
        assert strategy.id == "bollinger"

    def test_config(self):
        strategy = BollingerStrategy()
        config = strategy.config
        assert config.id == "bollinger"
        assert config.name == "布林带策略"
        assert config.category == "volatility"
        assert len(config.parameters) == 2
        param_keys = {p.key for p in config.parameters}
        assert param_keys == {"period", "std_dev"}

    def test_min_warmup_bars(self):
        strategy = BollingerStrategy()
        # period(20) = 20
        assert strategy.min_warmup_bars == 20

    def test_required_columns(self):
        strategy = BollingerStrategy()
        assert strategy.required_columns == {"close"}


class TestBollingerValidation:
    """参数校验测试"""

    def test_valid_params(self):
        strategy = BollingerStrategy()
        errors = strategy.validate_params({"period": 20, "std_dev": 2.0})
        assert errors == []

    def test_missing_params_use_defaults(self):
        strategy = BollingerStrategy()
        errors = strategy.validate_params({})
        # 布林带没有跨参数校验规则，默认参数总是合法
        assert errors == []


class TestBollingerSignals:
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

    def test_lower_band_buy(self):
        """价格触及下轨 → buy"""
        # 横盘建立中轨和带宽，然后大跌触及下轨
        prices = [100.0] * 25 + [95.0, 90.0, 85.0, 92.0]
        df = self._make_df(prices)
        strategy = BollingerStrategy()
        signals = strategy.generate_signals(df, {"period": 20, "std_dev": 2.0})

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1

    def test_upper_band_sell(self):
        """价格触及上轨 → sell"""
        # 横盘建立中轨和带宽，然后大涨触及上轨
        prices = [100.0] * 25 + [105.0, 110.0, 115.0, 108.0]
        df = self._make_df(prices)
        strategy = BollingerStrategy()
        signals = strategy.generate_signals(df, {"period": 20, "std_dev": 2.0})

        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1

    def test_within_bands_no_signal(self):
        """价格在布林带内运行，无信号"""
        prices = [100.0] * 50  # 完全横盘
        df = self._make_df(prices)
        strategy = BollingerStrategy()
        signals = strategy.generate_signals(df, {"period": 20, "std_dev": 2.0})

        non_wait = [s for s in signals if s.action != "wait"]
        # 横盘时价格在带内，不应有穿越信号
        assert len(non_wait) == 0

    def test_signal_has_reason(self):
        """信号包含触发理由"""
        prices = [100.0] * 25 + [95.0, 90.0, 85.0, 92.0]
        df = self._make_df(prices)
        strategy = BollingerStrategy()
        signals = strategy.generate_signals(df, {"period": 20, "std_dev": 2.0})

        buy_signals = [s for s in signals if s.action == "buy"]
        if buy_signals:
            assert len(buy_signals[0].reasons) > 0

    def test_insufficient_data(self):
        """数据不足时返回空列表"""
        prices = [100.0] * 10  # 不够 warmup=20
        df = self._make_df(prices)
        strategy = BollingerStrategy()
        signals = strategy.generate_signals(df, {"period": 20, "std_dev": 2.0})
        assert signals == []

    def test_wider_bands_reduce_signals(self):
        """更宽的标准差倍数减少信号"""
        prices = [100.0] * 25 + [95.0, 90.0, 85.0, 92.0]
        df = self._make_df(prices)
        strategy = BollingerStrategy()

        signals_narrow = strategy.generate_signals(df, {"period": 20, "std_dev": 1.5})
        signals_wide = strategy.generate_signals(df, {"period": 20, "std_dev": 3.0})

        narrow_buy = len([s for s in signals_narrow if s.action == "buy"])
        wide_buy = len([s for s in signals_wide if s.action == "buy"])
        # 更宽的带宽应产生 ≤ 窄带的信号数量
        assert wide_buy <= narrow_buy

    def test_signal_entry_price_is_close(self):
        """信号的 entry_price 为当日收盘价"""
        prices = [100.0] * 25 + [95.0, 90.0, 85.0, 92.0]
        df = self._make_df(prices)
        strategy = BollingerStrategy()
        signals = strategy.generate_signals(df, {"period": 20, "std_dev": 2.0})

        buy_signals = [s for s in signals if s.action == "buy"]
        if buy_signals:
            row = df[df["date"] == buy_signals[0].date].iloc[0]
            assert buy_signals[0].entry_price == row["close"]
