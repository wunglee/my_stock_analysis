"""测试 SignalGenerator"""

from typing import Any

import pandas as pd
import pytest

from src.services.backtest.engine.signal_generator import SignalGenerator
from src.services.backtest.exceptions import InsufficientDataError
from src.services.backtest.strategies.base import (
    ITechnicalStrategy,
    Signal,
    StrategyConfig,
    StrategyParameter,
    ValidationRule,
)


class DummyStrategy:
    """用于测试 SignalGenerator 的最小策略实现"""

    def __init__(self, required_cols: set[str] = None, warmup: int = 5):
        self._required = required_cols or {"close"}
        self._warmup = warmup
        self._config = StrategyConfig(
            id="dummy",
            name="Dummy",
            description="test",
            category="trend",
            parameters=[],
            validation_rules=[],
        )

    @property
    def id(self) -> str:
        return "dummy"

    @property
    def config(self) -> StrategyConfig:
        return self._config

    @property
    def min_warmup_bars(self) -> int:
        return self._warmup

    @property
    def required_columns(self) -> set[str]:
        return self._required

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        return []

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> list[Signal]:
        return [
            Signal(date="2024-01-03", action="buy", entry_price=100.0, execution_price=None, reasons=["test"]),
            Signal(date="2024-01-01", action="wait", entry_price=None, execution_price=None, reasons=[]),
            Signal(date="2024-01-05", action="sell", entry_price=110.0, execution_price=None, reasons=["test"]),
        ]


class TestSignalGenerator:
    """SignalGenerator 测试"""

    def _make_df(self, rows: int = 10) -> pd.DataFrame:
        return pd.DataFrame({
            "date": [f"2024-01-{i+1:02d}" for i in range(rows)],
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.0] * rows,
            "volume": [1000] * rows,
        })

    def test_normal_generation(self):
        gen = SignalGenerator()
        strategy = DummyStrategy()
        df = self._make_df(10)

        signals = gen.generate(strategy, df, {})

        # 应返回 3 个信号
        assert len(signals) == 3
        # 按日期升序排列
        assert signals[0].date == "2024-01-01"
        assert signals[1].date == "2024-01-03"
        assert signals[2].date == "2024-01-05"

    def test_missing_columns(self):
        gen = SignalGenerator()
        strategy = DummyStrategy(required_cols={"close", "volume"})
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "close": [100.0],
            # 缺少 volume
        })

        with pytest.raises(InsufficientDataError) as exc:
            gen.generate(strategy, df, {})
        assert "volume" in str(exc.value)

    def test_insufficient_data_length(self):
        gen = SignalGenerator()
        strategy = DummyStrategy(warmup=20)
        df = self._make_df(5)  # 只有 5 条，不够 warmup=20

        with pytest.raises(InsufficientDataError) as exc:
            gen.generate(strategy, df, {})
        assert "数据条数不足" in str(exc.value)

    def test_exact_warmup_length(self):
        """数据条数恰好等于 warmup 时不应报错"""
        gen = SignalGenerator()
        strategy = DummyStrategy(warmup=5)
        df = self._make_df(5)

        signals = gen.generate(strategy, df, {})
        assert len(signals) == 3

    def test_empty_signals(self):
        """策略返回空信号列表时，SignalGenerator 也返回空列表"""
        class EmptyStrategy(DummyStrategy):
            def generate_signals(self, df, params):
                return []

        gen = SignalGenerator()
        strategy = EmptyStrategy()
        df = self._make_df(10)

        signals = gen.generate(strategy, df, {})
        assert signals == []
