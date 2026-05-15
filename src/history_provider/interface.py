"""
历史数据提供者接口

定义 IDataProvider + ICompositeProvider Protocol，
为 history_provider 体系提供统一的接口契约。
"""

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class IDataProvider(Protocol):
    """历史K线数据获取统一接口

    所有实现只负责从自己的存储范围内取数据，不做缺失判断，不做跨层回写。

    约定:
    - 返回 DataFrame 的列名为: trade_date, open, high, low, close, volume
    - trade_date 为 datetime64[ns] 类型
    - 无数据时返回 None（不是空 DataFrame）
    - period 参数仅用于接口统一，叶子节点内部永远处理日线
    """

    def fetch(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        period: str = 'daily',
    ) -> pd.DataFrame | None:
        """获取历史K线数据

        Args:
            symbol: 证券代码
            start_date: 开始日期（包含）
            end_date: 结束日期（包含）
            period: 周期，'daily' | 'weekly' | 'monthly'

        Returns:
            DataFrame，列: trade_date, open, high, low, close, volume
            无数据返回 None
        """
        ...


@runtime_checkable
class ICompositeProvider(IDataProvider, Protocol):
    """组合模式接口 — 管理子提供者列表"""

    @property
    def providers(self) -> list[IDataProvider]:
        """返回管理的子提供者列表"""
        ...

    def add_provider(self, provider: IDataProvider) -> None:
        """添加子提供者"""
        ...

    def remove_provider(self, provider: IDataProvider) -> None:
        """移除子提供者"""
        ...
