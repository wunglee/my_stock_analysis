"""缓存优先的数据提供者

组装 IBarRepository + IExternalDataSource + ITradingCalendar + IBarAggregator，
实现"先查磁盘 → 缺失补全 → 自动保存 → 返回完整数据"的完整链路。
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from datetime import date as date_type
from typing import Optional

import pandas as pd

from src.data_provider.interfaces import (
    IBarAggregator,
    IBarRepository,
    IExternalDataSource,
    ITradingCalendar,
)

logger = logging.getLogger(__name__)

# 外部数据源拉取超时（秒），超时后回退到缓存数据
_EXTERNAL_FETCH_TIMEOUT = 10


class CachingDataProvider:
    """缓存优先的 K线数据提供者

    Args:
        repository: 磁盘缓存仓储（SQLite）
        external_source: 外部数据源（DataFetcherManager 适配器）
        calendar: 交易日历（用于缺失区间计算）
        aggregator: K线聚合器（日→周/月），周月线功能必需
    """

    def __init__(
        self,
        repository: IBarRepository,
        external_source: IExternalDataSource,
        calendar: ITradingCalendar,
        aggregator: Optional[IBarAggregator] = None,
    ) -> None:
        self._repository = repository
        self._external = external_source
        self._calendar = calendar
        self._aggregator = aggregator

        # 空数据冷却期：外部数据源还没有最新 1-2 天的数据时，
        # 记住 symbol → (latest_empty_end_date, expiry_timestamp)，
        # 冷却期内跳过重复拉取，避免每次请求都触发 10s 超时。
        self._empty_cooldown: dict[str, tuple[pd.Timestamp, float]] = {}

    def _is_in_empty_cooldown(self, symbol: str, range_end: pd.Timestamp) -> bool:
        """检查 range_end 是否在空数据冷却期内"""
        if symbol not in self._empty_cooldown:
            return False
        empty_date, expiry = self._empty_cooldown[symbol]
        if time.time() >= expiry:
            del self._empty_cooldown[symbol]
            return False
        return range_end <= empty_date

    # ------------------------------------------------------------------ #
    # Daily bars
    # ------------------------------------------------------------------ #
    def _normalize_date(self, ts: pd.Timestamp) -> pd.Timestamp:
        """统一为日期零点 Timestamp（naive 时间戳自动补全时区）"""
        if ts is None:
            return ts
        ts = pd.Timestamp(ts)
        if ts.tz is None and self._calendar.tz is not None:
            ts = ts.tz_localize(self._calendar.tz)
        return ts.normalize()

    def _fetch_external_with_timeout(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """带超时的外部数据拉取，超时返回 None（不阻塞等待后台线程）"""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                self._external.fetch_daily_bars, symbol, start_date, end_date
            )
            return future.result(timeout=_EXTERNAL_FETCH_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "[%s] External fetch timed out after %ds, falling back to cache",
                symbol,
                _EXTERNAL_FETCH_TIMEOUT,
            )
            return None
        finally:
            # wait=False: 超时后不阻塞等待后台线程，线程自行结束
            executor.shutdown(wait=False)

    def get_daily_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        *,
        use_cache: bool = True,
        force_refresh: bool = False,
        auto_save: bool = True,
    ) -> pd.DataFrame | None:
        """获取日线数据（缓存优先）

        Returns:
            标准 OHLCV DataFrame，无数据返回 None
        """
        start_date = self._normalize_date(start_date)
        end_date = self._normalize_date(end_date)

        # 0. 将 end_date 截断到最近有效收盘日，避免请求盘前/盘中不存在的
        #    未来数据，触发外部数据源链式超时（如 Efinance 6-7s）。
        effective_end = self._calendar.get_effective_trading_date(symbol)
        if effective_end < end_date:
            logger.debug(
                "[%s] end_date capped: %s -> %s (effective trading date)",
                symbol,
                end_date.strftime("%Y-%m-%d"),
                effective_end.strftime("%Y-%m-%d"),
            )
            end_date = effective_end
            if end_date < start_date:
                return None

        # 1. 强制刷新时跳过缓存
        if force_refresh or not use_cache:
            return self._fetch_and_maybe_save(
                symbol, start_date, end_date, auto_save=auto_save
            )

        # 2. 查询缓存
        cached = self._repository.get_daily_bars(symbol, start_date, end_date)

        # 3. 计算缺失区间
        missing_ranges = self._repository.get_missing_ranges(
            symbol, start_date, end_date
        )

        # 4. 无缺失，直接返回缓存
        if not missing_ranges:
            logger.debug("[%s] Cache hit: %s ~ %s", symbol, start_date.date(), end_date.date())
            return cached

        # 5. 过滤处于空数据冷却期内的缺失区间（外部数据源还没有最新数据）
        active_missing = [
            (s, e) for s, e in missing_ranges
            if not self._is_in_empty_cooldown(symbol, e)
        ]
        if not active_missing:
            logger.debug(
                "[%s] All %d missing ranges in empty cooldown, using cache",
                symbol,
                len(missing_ranges),
            )
            return cached

        # 6. 将所有活跃缺失区间合并为一次外部拉取
        merged_start = min(s for s, _ in active_missing)
        merged_end = max(e for _, e in active_missing)
        logger.info(
            "[%s] Cache partial miss, %d missing ranges merged to %s ~ %s",
            symbol,
            len(active_missing),
            merged_start.strftime("%Y-%m-%d"),
            merged_end.strftime("%Y-%m-%d"),
        )

        fetched = self._fetch_external_with_timeout(symbol, merged_start, merged_end)
        if fetched is None or fetched.empty:
            self._empty_cooldown[symbol] = (
                merged_end,
                time.time() + 14400,
            )
            logger.warning(
                "[%s] External fetch returned no data, cooldown until %s, using cache",
                symbol,
                pd.Timestamp(self._empty_cooldown[symbol][1], unit="s").strftime("%H:%M"),
            )
            return cached

        # 7. 拉取成功，清除该 symbol 的空数据冷却期
        self._empty_cooldown.pop(symbol, None)

        # 8. 自动保存到缓存
        if auto_save:
            saved = self._repository.save_daily_bars(fetched, symbol)
            logger.info("[%s] Auto-saved %d daily bars to cache", symbol, saved)

        # 9. 合并缓存 + 外部数据返回
        if cached is not None and not cached.empty:
            combined = pd.concat([cached, fetched], ignore_index=True)
            combined = combined.drop_duplicates(subset=["trade_date"], keep="last")
            combined = combined.sort_values("trade_date").reset_index(drop=True)
            # 过滤到请求区间（统一转为 date 对象避免 aware/naive dtype 比较错误）
            combined["_date"] = pd.to_datetime(combined["trade_date"]).dt.date
            mask = (combined["_date"] >= start_date.date()) & (combined["_date"] <= end_date.date())
            result = combined.drop(columns=["_date"]).loc[mask].reset_index(drop=True)
            return result

        return fetched

    def _fetch_and_maybe_save(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        auto_save: bool = True,
    ) -> pd.DataFrame | None:
        """直接请求外部数据，可选保存（也使用超时保护）"""
        df = self._fetch_external_with_timeout(symbol, start_date, end_date)
        if df is None or df.empty:
            return None

        if auto_save:
            saved = self._repository.save_daily_bars(df, symbol)
            logger.info("[%s] Auto-saved %d daily bars (force refresh)", symbol, saved)

        return df

    # ------------------------------------------------------------------ #
    # Weekly / Monthly bars
    # ------------------------------------------------------------------ #
    def get_weekly_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        *,
        use_cache: bool = True,
        force_refresh: bool = False,
        auto_save: bool = True,
    ) -> pd.DataFrame | None:
        """获取周线数据（基于日线聚合）

        策略：
        1. 先查已缓存的完整周线
        2. 获取所需区间的日线数据
        3. 聚合为周线，过滤未完成周
        4. 完整周线保存到缓存（供下次直接使用）
        """
        if self._aggregator is None:
            raise RuntimeError("IBarAggregator required for weekly bars")

        # 1. 查询已缓存的完整周线（不含当前未完成周）
        cached = None
        if use_cache and not force_refresh:
            cached = self._repository.get_weekly_bars(symbol, start_date, end_date)

        # 2. 获取日线数据（会自动走缓存优先逻辑）
        daily = self.get_daily_bars(
            symbol,
            start_date,
            end_date,
            use_cache=use_cache,
            force_refresh=force_refresh,
            auto_save=auto_save,
        )
        if daily is None or daily.empty:
            return cached

        # 3. 聚合为周线
        weekly = self._aggregator.daily_to_weekly(daily)
        if weekly.empty:
            return cached

        # 4. 过滤未完成周
        today = pd.Timestamp.now(tz="Asia/Shanghai").normalize()
        weekly = self._aggregator.filter_complete_periods(weekly, "weekly", today)

        # 5. 保存完整周线到缓存
        if auto_save and not weekly.empty:
            self._repository.save_weekly_bars(weekly, symbol)

        return weekly if not weekly.empty else cached

    def get_monthly_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        *,
        use_cache: bool = True,
        force_refresh: bool = False,
        auto_save: bool = True,
    ) -> pd.DataFrame | None:
        """获取月线数据（基于日线聚合）"""
        if self._aggregator is None:
            raise RuntimeError("IBarAggregator required for monthly bars")

        cached = None
        if use_cache and not force_refresh:
            cached = self._repository.get_monthly_bars(symbol, start_date, end_date)

        daily = self.get_daily_bars(
            symbol,
            start_date,
            end_date,
            use_cache=use_cache,
            force_refresh=force_refresh,
            auto_save=auto_save,
        )
        if daily is None or daily.empty:
            return cached

        monthly = self._aggregator.daily_to_monthly(daily)
        if monthly.empty:
            return cached

        today = pd.Timestamp.now(tz="Asia/Shanghai").normalize()
        monthly = self._aggregator.filter_complete_periods(monthly, "monthly", today)

        if auto_save and not monthly.empty:
            self._repository.save_monthly_bars(monthly, symbol)

        return monthly if not monthly.empty else cached
