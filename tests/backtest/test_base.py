"""测试核心数据结构：Signal、StrategyConfig、StrategyParameter、ValidationRule、ITechnicalStrategy"""

from dataclasses import FrozenInstanceError
from typing import Any

import pandas as pd
import pytest

from src.services.backtest.strategies.base import (
    ITechnicalStrategy,
    Signal,
    StrategyConfig,
    StrategyParameter,
    ValidationRule,
)


class TestSignal:
    """Signal frozen dataclass 测试"""

    def test_create_basic(self):
        signal = Signal(
            date="2024-01-15",
            action="buy",
            entry_price=100.5,
            execution_price=None,
            reasons=["金叉形成"],
        )
        assert signal.date == "2024-01-15"
        assert signal.action == "buy"
        assert signal.entry_price == 100.5
        assert signal.execution_price is None
        assert signal.reasons == ("金叉形成",)

    def test_create_wait_signal(self):
        signal = Signal(
            date="2024-01-15",
            action="wait",
            entry_price=None,
            execution_price=None,
            reasons=[],
        )
        assert signal.action == "wait"
        assert signal.entry_price is None

    def test_frozen_cannot_modify(self):
        signal = Signal(
            date="2024-01-15",
            action="buy",
            entry_price=100.0,
            execution_price=None,
            reasons=["test"],
        )
        with pytest.raises(FrozenInstanceError):
            signal.action = "sell"

    def test_equality(self):
        s1 = Signal(date="2024-01-15", action="buy", entry_price=100.0, execution_price=None, reasons=["test"])
        s2 = Signal(date="2024-01-15", action="buy", entry_price=100.0, execution_price=None, reasons=["test"])
        s3 = Signal(date="2024-01-16", action="buy", entry_price=100.0, execution_price=None, reasons=["test"])
        assert s1 == s2
        assert s1 != s3

    def test_hashable(self):
        s1 = Signal(date="2024-01-15", action="buy", entry_price=100.0, execution_price=None, reasons=["test"])
        s2 = Signal(date="2024-01-15", action="buy", entry_price=100.0, execution_price=None, reasons=["test"])
        assert hash(s1) == hash(s2)


class TestStrategyParameter:
    """StrategyParameter frozen dataclass 测试"""

    def test_create_number_param(self):
        param = StrategyParameter(
            key="short_period",
            name="短期均线周期",
            type="number",
            default_value=5,
            min=2,
            max=60,
            step=1,
        )
        assert param.key == "short_period"
        assert param.type == "number"
        assert param.default_value == 5
        assert param.min == 2

    def test_create_boolean_param(self):
        param = StrategyParameter(
            key="use_filter",
            name="启用过滤",
            type="boolean",
            default_value=True,
        )
        assert param.type == "boolean"
        assert param.min is None
        assert param.max is None

    def test_frozen(self):
        param = StrategyParameter(key="x", name="X", type="number", default_value=1)
        with pytest.raises(FrozenInstanceError):
            param.default_value = 2


class TestValidationRule:
    """ValidationRule frozen dataclass 测试"""

    def test_create_less_than(self):
        rule = ValidationRule(
            type="lessThan",
            param_a="short_period",
            param_b="long_period",
            message="短期周期必须小于长期周期",
        )
        assert rule.type == "lessThan"
        assert rule.param_a == "short_period"

    def test_create_greater_than(self):
        rule = ValidationRule(
            type="greaterThan",
            param_a="fast",
            param_b="slow",
            message="快线周期必须大于慢线周期",
        )
        assert rule.type == "greaterThan"

    def test_frozen(self):
        rule = ValidationRule(type="lessThan", param_a="a", param_b="b", message="msg")
        with pytest.raises(FrozenInstanceError):
            rule.param_a = "c"


class TestStrategyConfig:
    """StrategyConfig frozen dataclass 测试"""

    def test_create_dual_ma_config(self):
        config = StrategyConfig(
            id="dual_ma",
            name="双均线策略",
            description="基于短期和长期均线交叉产生买卖信号",
            category="trend",
            parameters=[
                StrategyParameter(
                    key="short_period",
                    name="短期均线周期",
                    type="number",
                    default_value=5,
                    min=2,
                    max=60,
                    step=1,
                ),
                StrategyParameter(
                    key="long_period",
                    name="长期均线周期",
                    type="number",
                    default_value=20,
                    min=5,
                    max=250,
                    step=1,
                ),
            ],
            validation_rules=[
                ValidationRule(
                    type="lessThan",
                    param_a="short_period",
                    param_b="long_period",
                    message="短期周期必须小于长期周期",
                ),
            ],
        )
        assert config.id == "dual_ma"
        assert len(config.parameters) == 2
        assert len(config.validation_rules) == 1
        assert config.category == "trend"

    def test_frozen(self):
        config = StrategyConfig(
            id="test",
            name="Test",
            description="desc",
            category="trend",
            parameters=[],
            validation_rules=[],
        )
        with pytest.raises(FrozenInstanceError):
            config.name = "Changed"


class MockStrategy:
    """用于测试 Protocol 的最小策略实现"""

    def __init__(self):
        self._config = StrategyConfig(
            id="mock",
            name="Mock",
            description="Mock strategy for testing",
            category="trend",
            parameters=[],
            validation_rules=[],
        )

    @property
    def id(self) -> str:
        return "mock"

    @property
    def config(self) -> StrategyConfig:
        return self._config

    @property
    def min_warmup_bars(self) -> int:
        return 10

    @property
    def required_columns(self) -> set[str]:
        return {"close"}

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        return []

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> list[Signal]:
        return []


class TestITechnicalStrategy:
    """ITechnicalStrategy Protocol 结构验证"""

    def test_mock_is_instance(self):
        strategy = MockStrategy()
        assert isinstance(strategy, ITechnicalStrategy)

    def test_mock_properties(self):
        strategy = MockStrategy()
        assert strategy.id == "mock"
        assert strategy.config.id == "mock"
        assert strategy.min_warmup_bars == 10
        assert strategy.required_columns == {"close"}

    def test_mock_validate_params(self):
        strategy = MockStrategy()
        errors = strategy.validate_params({})
        assert errors == []

    def test_mock_generate_signals(self):
        strategy = MockStrategy()
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        signals = strategy.generate_signals(df, {})
        assert signals == []

    def test_missing_method_not_protocol(self):
        class Incomplete:
            @property
            def id(self):
                return "incomplete"

        incomplete = Incomplete()
        assert not isinstance(incomplete, ITechnicalStrategy)
