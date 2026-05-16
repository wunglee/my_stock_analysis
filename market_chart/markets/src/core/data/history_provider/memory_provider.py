"""
内存缓存提供者 — 只缓存日线

存储: dict[str, pd.DataFrame]  # symbol -> DataFrame(trade_date, open, ...)
特性:
- 无窗口概念，直接按日期范围过滤
- merge + drop_duplicates 实现 upsert
- known_empty 按日期区间记录
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class MemoryCacheProvider:
    """内存缓存 — 只存日线

    存储结构:
        _data: dict[symbol -> DataFrame(trade_date, open, high, low, close, volume)]
        _earliest_date: dict[symbol -> Timestamp]  # 该symbol的最早已知日期
        _known_empty: dict[symbol -> list[(start, end)]]  # 已知无数据的区间列表
    """

    def __init__(self) -> None:
        self._data: Dict[str, pd.DataFrame] = {}
        self._earliest_date: Dict[str, pd.Timestamp] = {}
        self._known_empty: Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]] = {}

    # === IDataProvider 接口 ===

    def fetch(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        period: str = "daily",
    ) -> pd.DataFrame | None:
        """获取指定日期范围内的日线数据

        period 参数仅用于接口统一，内部永远返回日线。
        ThreeLayerProvider 在需要周/月线时自己对日线做聚合。
        调用方（ThreeLayerProvider）保证传入的 start_date/end_date 为 tz-naive。

        Returns:
            DataFrame 或 None（无数据时）
        """
        df = self._data.get(symbol)
        if df is None or df.empty:
            return None

        # 按日期范围过滤（调用方已统一为 tz-naive）
        mask = (df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)
        result = df.loc[mask].copy()

        if result.empty:
            return None

        return result.reset_index(drop=True)

    # === 回写方法（不在 IDataProvider 接口上） ===

    def set(self, symbol: str, df: pd.DataFrame) -> None:
        """写入或合并数据（upsert）

        合并策略:
        1. 新 symbol：直接存储
        2. 已有 symbol：concat 后按 trade_date 去重，保留后写入的
        3. 更新 earliest_date
        4. 清除与新数据重叠的 known_empty 标记
        """
        if df is None or df.empty:
            logger.debug(f"[Memory] 尝试写入空数据，忽略: {symbol}")
            return

        # 确保 trade_date 是 datetime 类型
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        existing = self._data.get(symbol)
        if existing is not None and not existing.empty:
            merged = pd.concat([existing, df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["trade_date"], keep="last")
            merged = merged.sort_values("trade_date").reset_index(drop=True)
            self._data[symbol] = merged
        else:
            self._data[symbol] = df.sort_values("trade_date").reset_index(drop=True)

        # 更新最早日期
        current_min = df["trade_date"].min()
        if symbol not in self._earliest_date or current_min < self._earliest_date[symbol]:
            self._earliest_date[symbol] = current_min

        # 清除与新数据重叠的 known_empty
        self._clear_known_empty_for_range(symbol, current_min, df["trade_date"].max())

        logger.info(f"[Memory] {symbol} 写入 {len(df)} 行，当前共 {len(self._data[symbol])} 行")

    # === known_empty 管理 ===

    def mark_known_empty(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> None:
        """标记指定区间为已知空（查询过确认无数据）"""
        if symbol not in self._known_empty:
            self._known_empty[symbol] = []
        self._known_empty[symbol].append((start_date, end_date))
        logger.debug(f"[Memory] {symbol} 标记空区间: {start_date.date()} ~ {end_date.date()}")

    def is_known_empty(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> bool:
        """检查请求区间是否完全落在某个 known_empty 区间内"""
        empty_ranges = self._known_empty.get(symbol, [])
        for empty_start, empty_end in empty_ranges:
            if start_date >= empty_start and end_date <= empty_end:
                return True
        return False

    def _clear_known_empty_for_range(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> None:
        """当新数据写入时，清除与数据范围重叠的 known_empty 标记"""
        if symbol not in self._known_empty:
            return

        remaining = []
        for empty_start, empty_end in self._known_empty[symbol]:
            # 如果 known_empty 区间与新数据范围有重叠，则丢弃
            if empty_end < start_date or empty_start > end_date:
                remaining.append((empty_start, empty_end))

        self._known_empty[symbol] = remaining

    # === 辅助方法 ===

    def get_earliest_date(self, symbol: str) -> pd.Timestamp | None:
        """获取该 symbol 的最早已知日期"""
        return self._earliest_date.get(symbol)

    def clear(self, symbol: str | None = None) -> None:
        """清空缓存

        Args:
            symbol: 指定 symbol 则只清空该 symbol，None 则清空全部
        """
        if symbol is None:
            self._data.clear()
            self._earliest_date.clear()
            self._known_empty.clear()
            logger.info("[Memory] 全部缓存已清空")
        else:
            self._data.pop(symbol, None)
            self._earliest_date.pop(symbol, None)
            self._known_empty.pop(symbol, None)
            logger.info(f"[Memory] {symbol} 缓存已清空")

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            "symbols": list(self._data.keys()),
            "total_symbols": len(self._data),
            "total_rows": sum(len(df) for df in self._data.values()),
            "known_empty_ranges": {
                sym: len(ranges) for sym, ranges in self._known_empty.items()
            },
        }
