"""交易日历适配器测试

验证 XCalTradingCalendar 将 exchange-calendars 封装为 ITradingCalendar。
所有日期操作使用带时区的 pd.Timestamp，符合事实标准。
"""

import pandas as pd
import pytest

from src.data_provider.interfaces import ITradingCalendar


class TestXCalTradingCalendar:
    """XCalTradingCalendar 适配器功能测试"""

    @pytest.fixture
    def calendar(self):
        from src.data_provider.trading_calendar_adapter import XCalTradingCalendar

        return XCalTradingCalendar(market="cn")

    def test_implements_protocol(self, calendar):
        assert isinstance(calendar, ITradingCalendar)

    def test_is_trading_day_known_holiday(self, calendar):
        """2024-10-01 是国庆，A股休市"""
        holiday = pd.Timestamp("2024-10-01", tz="Asia/Shanghai")
        assert calendar.is_trading_day(holiday) is False

    def test_is_trading_day_normal_trading_day(self, calendar):
        """2024-10-08 是国庆后第一个交易日"""
        trading_day = pd.Timestamp("2024-10-08", tz="Asia/Shanghai")
        assert calendar.is_trading_day(trading_day) is True

    def test_trading_days_between(self, calendar):
        """2024-10-08 到 2024-10-11 之间应包含 4 个交易日（排除周末）"""
        start = pd.Timestamp("2024-10-08", tz="Asia/Shanghai")
        end = pd.Timestamp("2024-10-11", tz="Asia/Shanghai")
        days = calendar.trading_days_between(start, end)
        assert len(days) == 4
        assert all(isinstance(d, pd.Timestamp) for d in days)
        assert all(d.tz is not None for d in days)

    def test_trading_days_between_excludes_holiday(self, calendar):
        """跨越国庆假期的区间应正确排除休市日"""
        start = pd.Timestamp("2024-09-30", tz="Asia/Shanghai")
        end = pd.Timestamp("2024-10-08", tz="Asia/Shanghai")
        days = calendar.trading_days_between(start, end)
        dates = [d.strftime("%Y-%m-%d") for d in days]
        assert "2024-10-01" not in dates
        assert "2024-10-08" in dates

    def test_next_trading_day_skips_weekend(self, calendar):
        """周五的下一个交易日是下周一"""
        friday = pd.Timestamp("2024-10-11", tz="Asia/Shanghai")
        nxt = calendar.next_trading_day(friday)
        assert nxt.strftime("%Y-%m-%d") == "2024-10-14"

    def test_prev_trading_day_skips_weekend(self, calendar):
        """周一的上一个交易日是上周五"""
        monday = pd.Timestamp("2024-10-14", tz="Asia/Shanghai")
        prev = calendar.prev_trading_day(monday)
        assert prev.strftime("%Y-%m-%d") == "2024-10-11"

    def test_naive_timestamp_raises(self, calendar):
        """不带时区的输入应抛出 ValueError"""
        naive = pd.Timestamp("2024-10-08")
        with pytest.raises(ValueError, match="timezone"):
            calendar.is_trading_day(naive)


class TestTradingCalendarEdgeCases:
    """边界条件与异常处理"""

    def test_raise_when_xcals_unavailable(self, monkeypatch):
        """exchange-calendars 不可用时抛 RuntimeError，不允许静默 fail-open"""
        monkeypatch.setattr(
            "src.data_provider.trading_calendar_adapter._XCALS_AVAILABLE", False
        )
        from src.data_provider.trading_calendar_adapter import XCalTradingCalendar

        cal = XCalTradingCalendar(market="cn")
        day = pd.Timestamp("2024-10-01", tz="Asia/Shanghai")
        with pytest.raises(RuntimeError, match="无法加载交易日历"):
            cal.is_trading_day(day)

    def test_hk_market(self):
        """港股日历应识别港股休市（如台风假）"""
        from src.data_provider.trading_calendar_adapter import XCalTradingCalendar

        cal = XCalTradingCalendar(market="hk")
        # 2024-07-01 是香港特区成立纪念日，休市
        holiday = pd.Timestamp("2024-07-01", tz="Asia/Hong_Kong")
        assert cal.is_trading_day(holiday) is False
