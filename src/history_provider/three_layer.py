"""
三层缓存编排器 — 唯一知道全局的人

职责:
1. 接收请求 (symbol, start, end, period)
2. 查 Memory（日线）→ 缺失检测 → 记录缺失区间
3. 查 DB（日线）→ 缺失检测 → 回写 Memory
4. 对剩余缺失 → MultiSource.fetch_daily(缺失区间)
5. MultiSource 命中 → 回写 Memory + DB
6. 如果 period=weekly/monthly → 对取到的日线执行聚合
7. 合并所有数据 → 返回完整 DataFrame

关键: 周/月线不在 Memory/DB 中缓存，每次实时聚合。
      因此不存在"陈旧K柱"问题。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import pandas as pd

from .interface import IDataProvider

logger = logging.getLogger(__name__)


class ThreeLayerProvider:
    """三层缓存编排器

    组合 MemoryCacheProvider + DbProvider + MultiSourceProvider，
    统一缺失检测、周期聚合、回写链条。
    """

    def __init__(
        self,
        memory,
        db,
        multi_source,
        calendar,
        bar_aggregator=None,
    ) -> None:
        """初始化

        Args:
            memory: MemoryCacheProvider 实例
            db: DbProvider 实例
            multi_source: MultiSourceProvider 实例
            calendar: 交易日历对象（需实现 trading_days_between, next_trading_day）
            bar_aggregator: BarAggregator 实例，None 时自动创建
        """
        self._memory = memory
        self._db = db
        self._multi_source = multi_source
        self._calendar = calendar

        # 延迟导入避免循环依赖
        if bar_aggregator is None:
            from src.data_provider.bar_aggregator import BarAggregator
            bar_aggregator = BarAggregator()
        self._bar_aggregator = bar_aggregator

    # ------------------------------------------------------------------ #
    # IDataProvider implementation
    # ------------------------------------------------------------------ #
    def fetch(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        period: str = "daily",
    ) -> pd.DataFrame | None:
        """获取历史K线（三层缓存编排入口）

        Args:
            symbol: 证券代码
            start_date: 开始日期（包含）
            end_date: 结束日期（包含）
            period: 'daily' | 'weekly' | 'monthly'

        Returns:
            DataFrame，列: trade_date, open, high, low, close, volume
            无数据返回 None
        """
        try:
            return self._fetch_internal(symbol, start_date, end_date, period)
        except Exception as e:
            logger.exception(
                f"[ThreeLayer] {symbol} {start_date.date()}~{end_date.date()} 请求异常: {e}"
            )
            return None

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _fetch_internal(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        period: str,
    ) -> pd.DataFrame | None:
        """内部获取逻辑（不含异常兜底）"""
        all_data: List[pd.DataFrame] = []

        # === 第1层: Memory ===
        df_mem = self._safe_memory_fetch(symbol, start_date, end_date)
        if df_mem is not None:
            all_data.append(df_mem)
            missing_ranges = self._detect_missing(symbol, start_date, end_date, df_mem)
        else:
            missing_ranges = [(start_date, end_date)]

        logger.info(
            f"[ThreeLayer] {symbol} Memory: {len(df_mem) if df_mem is not None else 0} 行, "
            f"缺失区间: {missing_ranges}"
        )

        if not missing_ranges:
            return self._assemble_and_aggregate(all_data, period)

        # === 第2层: DB ===
        new_missing = []
        for ms, me in missing_ranges:
            if self._memory.is_known_empty(symbol, ms, me):
                logger.debug(f"[ThreeLayer] {symbol} {ms.date()}~{me.date()} 已知为空，跳过 DB")
                new_missing.append((ms, me))
                continue

            df_db = self._safe_db_fetch(symbol, ms, me)
            if df_db is not None:
                all_data.append(df_db)
                self._memory.set(symbol, df_db)
                sub_missing = self._detect_missing(symbol, ms, me, df_db)
                new_missing.extend(sub_missing)
            else:
                # DB 无数据，保留到 MultiSource 层处理
                # 不标记 known_empty：MultiSource 可能还能获取
                new_missing.append((ms, me))

        missing_ranges = new_missing
        logger.info(
            f"[ThreeLayer] {symbol} DB 后缺失区间: {missing_ranges}"
        )

        if not missing_ranges:
            return self._assemble_and_aggregate(all_data, period)

        # === 第3层: MultiSource ===
        for ms, me in missing_ranges:
            if self._memory.is_known_empty(symbol, ms, me):
                logger.debug(
                    f"[ThreeLayer] {symbol} {ms.date()}~{me.date()} 已知为空，跳过 MultiSource"
                )
                continue

            df_ext = self._safe_multi_source_fetch(symbol, ms, me)
            if df_ext is not None:
                all_data.append(df_ext)
                self._memory.set(symbol, df_ext)
                self._safe_db_save(symbol, df_ext)
            else:
                self._memory.mark_known_empty(symbol, ms, me)

        return self._assemble_and_aggregate(all_data, period)

    # ------------------------------------------------------------------ #
    # Safe wrappers (异常隔离)
    # ------------------------------------------------------------------ #
    def _safe_memory_fetch(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame | None:
        try:
            return self._memory.fetch(symbol, start, end)
        except Exception as e:
            logger.warning(f"[ThreeLayer] Memory fetch 异常: {e}")
            return None

    def _safe_db_fetch(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame | None:
        try:
            return self._db.fetch(symbol, start, end)
        except Exception as e:
            logger.warning(f"[ThreeLayer] DB fetch 异常: {e}")
            return None

    def _safe_multi_source_fetch(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame | None:
        try:
            return self._multi_source.fetch_daily(symbol, start, end)
        except Exception as e:
            logger.warning(f"[ThreeLayer] MultiSource fetch 异常: {e}")
            return None

    def _safe_db_save(self, symbol: str, df: pd.DataFrame) -> None:
        try:
            self._db.save(symbol, df)
        except Exception as e:
            logger.warning(f"[ThreeLayer] DB save 回写异常（不影响返回）: {e}")

    # ------------------------------------------------------------------ #
    # Missing detection
    # ------------------------------------------------------------------ #
    def _detect_missing(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        df: pd.DataFrame,
    ) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
        """交易日粒度缺失检测

        算法:
        1. 从交易日历获取 [start, end] 内全部交易日
        2. 获取 df['trade_date'] 的日期集合
        3. 集合差 = 缺失交易日
        4. 排除上市前日期（symbol 在 Memory 中的最早记录日之前）
        5. 连续缺失日合并为区间列表
        """
        # 1. 获取区间全部交易日
        try:
            trading_days = self._calendar.trading_days_between(start, end)
        except Exception as e:
            logger.warning(f"[ThreeLayer] 交易日历查询异常: {e}")
            return []

        if not trading_days:
            return []

        # 2. 已覆盖的日期（统一为 tz-naive 的 date 对象比较）
        existing_dates = set(
            pd.to_datetime(df["trade_date"]).dt.tz_localize(None).dt.normalize()
        )

        # 3. 缺失交易日
        missing_days = [
            d for d in trading_days
            if pd.to_datetime(d).tz_localize(None).normalize() not in existing_dates
        ]
        if not missing_days:
            return []

        # 4. 排除上市前日期
        earliest = self._memory.get_earliest_date(symbol)
        if earliest is not None:
            earliest_norm = pd.to_datetime(earliest).tz_localize(None).normalize()
            missing_days = [
                d for d in missing_days
                if pd.to_datetime(d).tz_localize(None).normalize() >= earliest_norm
            ]

        if not missing_days:
            return []

        # 5. 连续缺失日合并为区间
        ranges = []
        range_start = missing_days[0]
        range_end = missing_days[0]

        for day in missing_days[1:]:
            try:
                expected_next = self._calendar.next_trading_day(range_end)
            except Exception:
                # 日历异常时，按自然日判断连续性
                expected_next = range_end + pd.Timedelta(days=1)

            day_ts = pd.to_datetime(day).tz_localize(None).normalize()
            expected_ts = pd.to_datetime(expected_next).tz_localize(None).normalize()

            if day_ts == expected_ts:
                range_end = day
            else:
                ranges.append((
                    pd.to_datetime(range_start).tz_localize(None).normalize(),
                    pd.to_datetime(range_end).tz_localize(None).normalize(),
                ))
                range_start = day
                range_end = day

        ranges.append((
            pd.to_datetime(range_start).tz_localize(None).normalize(),
            pd.to_datetime(range_end).tz_localize(None).normalize(),
        ))
        return ranges

    # ------------------------------------------------------------------ #
    # Assemble & aggregate
    # ------------------------------------------------------------------ #
    def _assemble_and_aggregate(
        self,
        dataframes: List[pd.DataFrame],
        period: str,
    ) -> pd.DataFrame | None:
        """合并多个 DataFrame，按需聚合为周/月线"""
        if not dataframes:
            return None

        merged = pd.concat(dataframes, ignore_index=True)
        merged = merged.drop_duplicates(subset=["trade_date"], keep="last")
        merged = merged.sort_values("trade_date").reset_index(drop=True)

        if merged.empty:
            return None

        if period == "daily":
            return merged

        if period == "weekly":
            return self._bar_aggregator.daily_to_weekly(merged)

        if period == "monthly":
            return self._bar_aggregator.daily_to_monthly(merged)

        raise ValueError(f"不支持的周期: {period}")
