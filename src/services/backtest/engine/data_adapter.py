"""数据适配器

将 CachingDataProvider 适配为回测服务层需要的 IDataFetcher 接口。
"""

from typing import Protocol

import pandas as pd


class IDataFetcher(Protocol):
    """数据获取器接口（回测服务层使用）

    与 CachingDataProvider 的区别：
    - 日期参数为 str 格式（YYYY-MM-DD）
    - 返回 DataFrame 的日期列为 str 格式
    - 列名为标准 OHLCV（date/open/high/low/close/volume）
    """

    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取日线数据

        Returns:
            DataFrame 含 date/open/high/low/close/volume 列；无数据返回 None
        """
        ...


class CachingDataProviderAdapter:
    """CachingDataProvider 适配器

    职责：
    1. 日期格式转换：str → pd.Timestamp
    2. 列名映射：trade_date → date
    3. 结果排序：按 date 升序
    """

    def __init__(self, provider):
        """Args:
            provider: CachingDataProvider 实例
        """
        self._provider = provider

    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取日线数据"""
        df = self._provider.get_daily_bars(
            symbol,
            pd.Timestamp(start_date),
            pd.Timestamp(end_date),
        )
        if df is None or df.empty:
            return None

        # 列名映射：trade_date → date
        if "trade_date" in df.columns:
            df = df.rename(columns={"trade_date": "date"})

        # 确保 date 列为字符串
        df["date"] = df["date"].astype(str)

        # 按日期升序排列
        df = df.sort_values("date").reset_index(drop=True)

        return df
