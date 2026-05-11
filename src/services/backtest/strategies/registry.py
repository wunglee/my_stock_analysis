"""策略注册表

**有意识取舍**：当前采用硬编码注册（手动导入策略类并注册）。
策略数量 <10 个时，硬编码更简单、类型安全、IDE 友好。
策略数量超过 10 个时建议引入自动发现机制（目录扫描 + 动态导入）。
"""

import threading

from src.services.backtest.strategies.base import ITechnicalStrategy, StrategyConfig


class StrategyRegistry:
    """策略注册表

    管理所有可用策略的注册与查询。线程安全（只读操作，初始化后不改）。
    """

    def __init__(self):
        self._strategies: dict[str, ITechnicalStrategy] = {}

    def register(self, strategy: ITechnicalStrategy) -> None:
        """注册策略，同 ID 覆盖"""
        self._strategies[strategy.id] = strategy

    def get(self, strategy_id: str) -> ITechnicalStrategy:
        """按 ID 获取策略，不存在则抛出 KeyError"""
        if strategy_id not in self._strategies:
            raise KeyError(f"Strategy not found: {strategy_id}")
        return self._strategies[strategy_id]

    def list_all(self) -> list[StrategyConfig]:
        """列出所有已注册策略的配置"""
        return [s.config for s in self._strategies.values()]


# 模块级默认注册表实例（惰性初始化）
_default_registry: StrategyRegistry | None = None
_registry_lock = threading.Lock()


def get_default_registry() -> StrategyRegistry:
    """获取默认策略注册表（含所有内置策略）

    线程安全：多线程首次调用时通过锁保护初始化。
    多进程场景下每个进程独立初始化一次，是正常行为。
    """
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                registry = StrategyRegistry()
                registry.register(DualMAStrategy())
                registry.register(MACDStrategy())
                registry.register(RSIStrategy())
                registry.register(BollingerStrategy())
                _default_registry = registry
    return _default_registry


# 避免循环导入：在模块末尾导入策略类
from src.services.backtest.strategies.dual_ma import DualMAStrategy  # noqa: E402
from src.services.backtest.strategies.macd import MACDStrategy  # noqa: E402
from src.services.backtest.strategies.rsi import RSIStrategy  # noqa: E402
from src.services.backtest.strategies.bollinger import BollingerStrategy  # noqa: E402
