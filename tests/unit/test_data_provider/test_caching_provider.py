"""CachingDataProvider 测试

验证缓存优先、缺失补全、强制刷新、周月线聚合的完整链路。
"""

import pandas as pd
import pytest
import sqlalchemy as sa

from src.data_provider.interfaces import (
    IBarAggregator,
    IBarRepository,
    IExternalDataSource,
    ITradingCalendar,
)


class _FakeCalendar:
    """假交易日历：2024-10-08 到 10-11 都是交易日"""

    def __init__(self):
        self._days = pd.date_range("2024-10-08", periods=4, freq="D").tolist()

    def is_trading_day(self, date: pd.Timestamp) -> bool:
        return date.normalize() in [d.normalize() for d in self._days]

    def trading_days_between(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        return [d for d in self._days if start <= d <= end]

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        later = [d for d in self._days if d > date]
        return min(later) if later else date

    def prev_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        earlier = [d for d in self._days if d < date]
        return max(earlier) if earlier else date


class _FakeRepository:
    """内存中的假仓储，用于隔离测试"""

    def __init__(self):
        self._data: dict[str, pd.DataFrame] = {}

    def get_daily_bars(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame | None:
        df = self._data.get(symbol)
        if df is None or df.empty:
            return None
        mask = (df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)
        filtered = df.loc[mask]
        return filtered.reset_index(drop=True) if not filtered.empty else None

    def save_daily_bars(self, df: pd.DataFrame, symbol: str) -> int:
        if symbol not in self._data:
            self._data[symbol] = df.copy()
        else:
            existing = self._data[symbol]
            # 简单 UPSERT：删除重复日期后追加
            dates = set(df["trade_date"])
            existing = existing[~existing["trade_date"].isin(dates)]
            self._data[symbol] = pd.concat([existing, df], ignore_index=True)
            self._data[symbol] = self._data[symbol].sort_values("trade_date").reset_index(drop=True)
        return len(df)

    def get_date_range(self, symbol: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        df = self._data.get(symbol)
        if df is None or df.empty:
            return None
        return df["trade_date"].min(), df["trade_date"].max()

    def get_missing_ranges(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        # 简化：直接委托给日历判断
        cal = _FakeCalendar()
        all_days = cal.trading_days_between(start_date, end_date)
        df = self._data.get(symbol)
        if df is None:
            return [(start_date, end_date)] if all_days else []
        existing = set(df["trade_date"])
        missing = [d for d in all_days if d not in existing]
        if not missing:
            return []
        return [(min(missing), max(missing))]

    def get_weekly_bars(self, *args, **kwargs) -> pd.DataFrame | None:
        return None

    def save_weekly_bars(self, *args, **kwargs) -> int:
        return 0

    def get_monthly_bars(self, *args, **kwargs) -> pd.DataFrame | None:
        return None

    def save_monthly_bars(self, *args, **kwargs) -> int:
        return 0


class _FakeExternalSource:
    """假外部数据源，返回固定数据"""

    def __init__(self):
        self.call_count = 0
        self._last_source = "FakeSource"

    @property
    def source_name(self) -> str:
        return self._last_source

    def fetch_daily_bars(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame | None:
        self.call_count += 1
        days = pd.date_range(start=start_date, end=end_date, freq="D")
        df = pd.DataFrame({
            "trade_date": days,
            "open": [100.0 + i for i in range(len(days))],
            "high": [105.0 + i for i in range(len(days))],
            "low": [99.0 + i for i in range(len(days))],
            "close": [101.0 + i for i in range(len(days))],
            "volume": [1000.0 * (i + 1) for i in range(len(days))],
            "amount": [100000.0 * (i + 1) for i in range(len(days))],
        })
        return df


class TestCachingDataProvider:
    """CachingDataProvider 核心功能测试"""

    @pytest.fixture
    def provider(self):
        from src.data_provider.caching_provider import CachingDataProvider

        return CachingDataProvider(
            repository=_FakeRepository(),
            external_source=_FakeExternalSource(),
            calendar=_FakeCalendar(),
            aggregator=None,  # 周月线测试单独进行
        )

    def test_cache_miss_fetches_external(self, provider):
        """缓存未命中时触发外部请求"""
        result = provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert result is not None
        assert len(result) == 4
        # 外部数据源应被调用
        assert provider._external.call_count == 1

    def test_cache_hit_no_external_request(self, provider):
        """缓存命中时不应触发外部请求"""
        # 第一次调用：缓存未命中，请求外部
        provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert provider._external.call_count == 1

        # 第二次调用：缓存命中，不应再请求
        result = provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert result is not None
        assert len(result) == 4
        assert provider._external.call_count == 1  # 未增加

    def test_partial_cache_fills_gap(self, provider):
        """部分缓存时只请求缺失区间"""
        # 先存入部分数据（10/08-10/09）
        partial_df = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-08"), pd.Timestamp("2024-10-09")],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 2000.0],
            "amount": [100000.0, 200000.0],
        })
        provider._repository.save_daily_bars(partial_df, symbol="600519")

        # 请求完整区间（10/08-10/11）
        result = provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert result is not None
        assert len(result) == 4
        # 外部只被调用一次（请求 10/10-10/11）
        assert provider._external.call_count == 1

    def test_force_refresh_bypasses_cache(self, provider):
        """强制刷新时忽略缓存"""
        # 先缓存数据
        provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert provider._external.call_count == 1

        # 强制刷新
        result = provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
            force_refresh=True,
        )
        assert result is not None
        assert provider._external.call_count == 2  # 再次请求外部

    def test_use_cache_false_always_external(self, provider):
        """use_cache=False 时总是请求外部"""
        provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
            use_cache=False,
        )
        assert provider._external.call_count == 1

        # 再次调用，仍然请求外部
        provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
            use_cache=False,
        )
        assert provider._external.call_count == 2

    def test_auto_save_false_does_not_persist(self, provider):
        """auto_save=False 时不保存到缓存"""
        result = provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
            auto_save=False,
        )
        assert result is not None
        assert len(result) == 4

        # 再次调用，缓存未命中（因为没保存），再次请求外部
        provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert provider._external.call_count == 2


class TestCachingProviderEdgeCases:
    """边界条件"""

    def test_empty_external_response(self):
        """外部返回空数据时应优雅处理"""
        from src.data_provider.caching_provider import CachingDataProvider

        class EmptySource:
            @property
            def source_name(self): return "Empty"
            def fetch_daily_bars(self, *args, **kwargs): return None

        provider = CachingDataProvider(
            repository=_FakeRepository(),
            external_source=EmptySource(),
            calendar=_FakeCalendar(),
            aggregator=None,
        )

        result = provider.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert result is None
