"""
数据库适配 — 只操作 daily_bars

包装 SqliteBarRepository，但只使用其 daily 相关方法。
weekly/monthly_bars 表不再写入（保留兼容只读）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.data_provider.bar_repository import SqliteBarRepository

logger = logging.getLogger(__name__)


class DbProvider:
    """数据库适配 — 只操作 daily_bars

    职责:
    - fetch(): 从 daily_bars 取数据，返回 DataFrame | None
    - save(): 写入 daily_bars（upsert）

    注意:
    - period 参数仅用于接口统一，内部永远操作日线
    - 空 DataFrame / None 被统一转换为 None（fetch）或 0（save）
    """

    def __init__(self, repository: "SqliteBarRepository") -> None:
        self._repo = repository

    def fetch(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        period: str = "daily",
    ) -> pd.DataFrame | None:
        """从 daily_bars 取数据

        Args:
            symbol: 证券代码
            start_date: 开始日期（包含）
            end_date: 结束日期（包含）
            period: 仅用于接口统一，忽略

        Returns:
            DataFrame 或 None（无数据时）
        """
        df = self._repo.get_daily_bars(symbol, start_date, end_date)
        if df is None or df.empty:
            return None
        return df

    def save(self, symbol: str, df: pd.DataFrame | None) -> int:
        """写入 daily_bars（upsert）

        Args:
            symbol: 证券代码
            df: 要写入的 DataFrame

        Returns:
            实际写入/更新的记录数
        """
        if df is None or df.empty:
            logger.debug(f"[DbProvider] 尝试写入空数据，忽略: {symbol}")
            return 0

        return self._repo.save_daily_bars(df, symbol)
