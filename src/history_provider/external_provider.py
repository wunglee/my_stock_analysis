"""
外部数据源适配 — 单数据源标准化

包装单个 fetcher，标准化返回 DataFrame 列名为事实标准（trade_date）。
"""

from __future__ import annotations

import logging
from typing import Callable, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 常见列名映射（旧 -> 新）
_COLUMN_RENAME = {
    "date": "trade_date",
}

# 标准列集合
_STANDARD_COLS = {
    "open", "high", "low", "close", "volume", "amount",
    "pre_close", "change", "pct_chg", "turnover_rate",
}


class ExternalApiProvider:
    """单外部数据源适配 — 仅日线

    包装底层 fetcher（如 akshare/yahoo/tushare），
    将返回的 DataFrame 列名对齐为事实标准。

    fetcher 的接口约定:
        fetcher(symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp)
            -> pd.DataFrame | None
    """

    def __init__(
        self,
        name: str,
        fetcher: Callable[[str, pd.Timestamp, pd.Timestamp], pd.DataFrame | None],
    ) -> None:
        self._name = name
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        """数据源名称（用于日志/溯源）"""
        return self._name

    def fetch(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        period: str = "daily",
    ) -> pd.DataFrame | None:
        """获取日线数据并标准化

        Args:
            symbol: 证券代码
            start_date: 开始日期（包含）
            end_date: 结束日期（包含）
            period: 仅用于接口统一，忽略

        Returns:
            DataFrame columns: trade_date, open, high, low, close, volume[, ...]
            无数据返回 None
        """
        try:
            df = self._fetcher(symbol, start_date, end_date)
            if df is None or df.empty:
                return None
            return self._normalize(df, symbol)
        except Exception as e:
            logger.warning(f"[{self._name}] {symbol} 获取失败: {e}")
            return None

    def _normalize(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """标准化 DataFrame 列名和格式"""
        df = df.copy()

        # 1. 重命名列（date -> trade_date）
        df = df.rename(columns=_COLUMN_RENAME)

        # 2. 确保 trade_date 是 datetime
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])

        # 3. 添加 symbol 列（如果不存在）
        if "symbol" not in df.columns:
            df["symbol"] = symbol

        # 4. 过滤保留标准列 + symbol + trade_date
        keep_cols = ["symbol", "trade_date"] + [
            c for c in _STANDARD_COLS if c in df.columns
        ]
        available = [c for c in keep_cols if c in df.columns]
        df = df[available]

        # 5. 按日期排序
        df = df.sort_values("trade_date").reset_index(drop=True)

        return df
