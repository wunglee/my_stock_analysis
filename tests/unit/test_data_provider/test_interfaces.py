"""接口可导入与可实例化验证

RED phase: 先写测试，确保接口定义可以被正确导入、
被假实现实现，且 Protocol 检查生效。
"""

import pandas as pd
import pytest


class TestInterfaceImport:
    """验证所有接口可被导入"""

    def test_all_interfaces_importable(self):
        from src.data_provider.interfaces import (
            IBarAggregator,
            IBarRepository,
            IExternalDataSource,
            ITradingCalendar,
        )

        assert IBarRepository is not None
        assert IExternalDataSource is not None
        assert ITradingCalendar is not None
        assert IBarAggregator is not None


class TestTradingCalendarProtocol:
    """ITradingCalendar 的 Protocol 约束检查"""

    def test_valid_implementation_is_instance(self):
        from src.data_provider.interfaces import ITradingCalendar

        class FakeCalendar:
            def is_trading_day(self, date: pd.Timestamp) -> bool:
                return True

            def trading_days_between(
                self, start: pd.Timestamp, end: pd.Timestamp
            ) -> list[pd.Timestamp]:
                return []

            def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
                return date

            def prev_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
                return date

        assert isinstance(FakeCalendar(), ITradingCalendar)

    def test_missing_method_fails_protocol(self):
        from src.data_provider.interfaces import ITradingCalendar

        class BadCalendar:
            def is_trading_day(self, date: pd.Timestamp) -> bool:
                return True

            # 缺少其他方法

        assert not isinstance(BadCalendar(), ITradingCalendar)


class TestBarRepositoryProtocol:
    """IBarRepository 的 Protocol 约束检查"""

    def test_valid_implementation_is_instance(self):
        from src.data_provider.interfaces import IBarRepository

        class FakeRepo:
            def get_daily_bars(
                self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
            ) -> pd.DataFrame | None:
                return None

            def save_daily_bars(self, df: pd.DataFrame, symbol: str) -> int:
                return 0

            def get_weekly_bars(
                self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
            ) -> pd.DataFrame | None:
                return None

            def save_weekly_bars(self, df: pd.DataFrame, symbol: str) -> int:
                return 0

            def get_monthly_bars(
                self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
            ) -> pd.DataFrame | None:
                return None

            def save_monthly_bars(self, df: pd.DataFrame, symbol: str) -> int:
                return 0

            def get_date_range(
                self, symbol: str
            ) -> tuple[pd.Timestamp, pd.Timestamp] | None:
                return None

            def get_missing_ranges(
                self,
                symbol: str,
                start_date: pd.Timestamp,
                end_date: pd.Timestamp,
            ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
                return []

        assert isinstance(FakeRepo(), IBarRepository)


class TestExternalDataSourceProtocol:
    """IExternalDataSource 的 Protocol 约束检查"""

    def test_valid_implementation_is_instance(self):
        from src.data_provider.interfaces import IExternalDataSource

        class FakeSource:
            def fetch_daily_bars(
                self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
            ) -> pd.DataFrame | None:
                return None

            def fetch_fundamental(self, symbol: str) -> dict | None:
                return None

            @property
            def source_name(self) -> str:
                return "fake"

        assert isinstance(FakeSource(), IExternalDataSource)

    def test_missing_source_name_fails(self):
        from src.data_provider.interfaces import IExternalDataSource

        class BadSource:
            def fetch_daily_bars(
                self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp
            ) -> pd.DataFrame | None:
                return None

            # 缺少 source_name 属性

        assert not isinstance(BadSource(), IExternalDataSource)


class TestBarAggregatorProtocol:
    """IBarAggregator 的 Protocol 约束检查"""

    def test_valid_implementation_is_instance(self):
        from src.data_provider.interfaces import IBarAggregator

        class FakeAgg:
            def daily_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
                return df

            def daily_to_monthly(self, df: pd.DataFrame) -> pd.DataFrame:
                return df

            def filter_complete_periods(
                self, df: pd.DataFrame, period: str, today: pd.Timestamp
            ) -> pd.DataFrame:
                return df

        assert isinstance(FakeAgg(), IBarAggregator)
