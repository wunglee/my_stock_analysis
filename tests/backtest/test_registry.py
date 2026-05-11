"""测试 StrategyRegistry"""

import pytest

from src.services.backtest.strategies.base import StrategyConfig, StrategyParameter, ValidationRule
from src.services.backtest.strategies.dual_ma import DualMAStrategy
from src.services.backtest.strategies.registry import StrategyRegistry


class TestStrategyRegistry:
    """策略注册表测试"""

    def test_register_and_get(self):
        registry = StrategyRegistry()
        strategy = DualMAStrategy()
        registry.register(strategy)

        found = registry.get("dual_ma")
        assert found is strategy
        assert found.id == "dual_ma"

    def test_get_not_found(self):
        registry = StrategyRegistry()
        with pytest.raises(KeyError):
            registry.get("not_exist")

    def test_list_all_empty(self):
        registry = StrategyRegistry()
        configs = registry.list_all()
        assert configs == []

    def test_list_all_returns_configs(self):
        registry = StrategyRegistry()
        registry.register(DualMAStrategy())

        configs = registry.list_all()
        assert len(configs) == 1
        assert configs[0].id == "dual_ma"
        assert configs[0].name == "双均线策略"

    def test_register_duplicate_overwrites(self):
        registry = StrategyRegistry()
        s1 = DualMAStrategy()
        s2 = DualMAStrategy()
        registry.register(s1)
        registry.register(s2)

        assert registry.get("dual_ma") is s2
        assert len(registry.list_all()) == 1

    def test_default_registry_has_all_strategies(self):
        """默认注册表包含全部 4 个策略"""
        from src.services.backtest.strategies.registry import get_default_registry

        registry = get_default_registry()
        configs = registry.list_all()
        ids = {c.id for c in configs}
        assert ids == {"dual_ma", "macd", "rsi", "bollinger"}
