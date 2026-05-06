"""外部数据源适配器

将现有的 DataFetcherManager 包装为 IExternalDataSource 接口，
同时把返回的 DataFrame 列名对齐为事实标准。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from src.data_provider.interfaces import IExternalDataSource

if TYPE_CHECKING:
    from data_provider.base import DataFetcherManager

logger = logging.getLogger(__name__)

# 事实标准列名映射（旧 -> 新）
_COLUMN_RENAME = {
    "date": "trade_date",
}

# DataFetcherManager 返回的列中，属于事实标准的列
_STANDARD_COLS = {
    "open", "high", "low", "close", "volume", "amount",
    "pre_close", "change", "pct_chg", "turnover_rate",
}


class FetcherManagerDataSource:
    """DataFetcherManager 的 IExternalDataSource 适配器

    负责：
    1. 将 symbol/start_date/end_date 转发给 DataFetcherManager
    2. 将返回 DataFrame 的列名对齐为事实标准（date -> trade_date，添加 symbol）
    3. 剥离非标准列（ma5, ma10, ma20, volume_ratio, turnover_rate 等）
    """

    def __init__(self, manager: "DataFetcherManager") -> None:
        self._manager = manager
        self._last_source_name: str = ""

    @property
    def source_name(self) -> str:
        return self._last_source_name

    def fetch_daily_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """从 DataFetcherManager 获取日线数据并标准化"""
        try:
            # DataFetcherManager 接受 str 格式的日期
            start_str = start_date.strftime("%Y-%m-%d") if start_date else None
            end_str = end_date.strftime("%Y-%m-%d") if end_date else None

            df, source = self._manager.get_daily_data(
                stock_code=symbol,
                start_date=start_str,
                end_date=end_str,
            )
            self._last_source_name = source

            if df is None or df.empty:
                return None

            return self._normalize(df, symbol)

        except Exception as e:
            logger.warning("FetcherManagerDataSource.fetch_daily_bars failed: %s", e)
            return None

    def fetch_fundamental(self, symbol: str) -> dict | None:
        # 当前 DataFetcherManager 无统一基本面接口，返回 None
        return None

    def _normalize(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """将 DataFetcherManager 的输出标准化为事实标准格式"""
        df = df.copy()

        # 1. 重命名列
        df = df.rename(columns=_COLUMN_RENAME)

        # 2. 确保 trade_date 是 datetime
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])

        # 3. 添加 symbol 列
        df["symbol"] = symbol

        # 4. 过滤出标准列 + symbol + trade_date
        keep_cols = ["symbol", "trade_date"] + [
            c for c in _STANDARD_COLS if c in df.columns
        ]

        # 5. 保留存在的事实标准列，缺失的不管
        available = [c for c in keep_cols if c in df.columns]
        df = df[available]

        # 6. 按日期排序
        df = df.sort_values("trade_date").reset_index(drop=True)

        return df
