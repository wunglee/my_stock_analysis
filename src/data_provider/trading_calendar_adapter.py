"""交易日历适配器

将 exchange-calendars 封装为 ITradingCalendar 接口实现。
所有日期强制使用带时区的 pd.Timestamp，符合事实标准。
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

# 复用核心模块的 exchange-calendars 可用性检测
try:
    import exchange_calendars as xcals

    _XCALS_AVAILABLE = True
except ImportError:
    _XCALS_AVAILABLE = False

logger = logging.getLogger(__name__)

# market -> exchange code
_MARKET_EXCHANGE = {"cn": "XSHG", "hk": "XHKG", "us": "XNYS"}
# market -> IANA timezone
_MARKET_TZ = {"cn": "Asia/Shanghai", "hk": "Asia/Hong_Kong", "us": "America/New_York"}


class XCalTradingCalendar:
    """基于 exchange-calendars 的交易日历适配器

    Args:
        market: "cn" | "hk" | "us"
    """

    def __init__(self, market: str = "cn") -> None:
        self._market = market
        self._exchange = _MARKET_EXCHANGE.get(market)
        self._tz_name = _MARKET_TZ.get(market)
        self._tz = pd.Timestamp.now(tz=self._tz_name).tz if self._tz_name else None

    @property
    def tz(self):
        """时区信息，供下游适配器使用"""
        return self._tz

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_aware(self, ts: pd.Timestamp) -> pd.Timestamp:
        if ts.tz is None:
            raise ValueError(f"Timestamp must be timezone-aware, got naive: {ts}")
        return ts

    def _calendar(self):
        if not _XCALS_AVAILABLE or not self._exchange:
            return None
        try:
            return xcals.get_calendar(self._exchange)
        except Exception as e:
            logger.warning("Failed to load calendar for %s: %s", self._market, e)
            return None

    # ------------------------------------------------------------------ #
    # ITradingCalendar implementation
    # ------------------------------------------------------------------ #
    def is_trading_day(self, date: pd.Timestamp) -> bool:
        self._ensure_aware(date)
        cal = self._calendar()
        if cal is None:
            return True  # fail-open
        try:
            session = datetime(date.year, date.month, date.day)
            return cal.is_session(session)
        except Exception as e:
            logger.warning("is_trading_day fail-open: %s", e)
            return True

    def trading_days_between(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        self._ensure_aware(start)
        self._ensure_aware(end)
        cal = self._calendar()
        if cal is None:
            # fail-open: 返回自然日（闭区间）
            days = pd.date_range(start=start, end=end, freq="D", tz=start.tz)
            return [d for d in days]

        try:
            sessions = cal.sessions_in_range(
                start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            )
            tz = start.tz
            return [pd.Timestamp(s, tz=tz) for s in sessions]
        except Exception as e:
            logger.warning("trading_days_between fail-open: %s", e)
            days = pd.date_range(start=start, end=end, freq="D", tz=start.tz)
            return [d for d in days]

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        self._ensure_aware(date)
        cal = self._calendar()
        if cal is None:
            # fail-open: 下一个自然日
            return date + pd.Timedelta(days=1)
        try:
            # date_to_session 在日期本身是交易日时返回当天；
            # 我们需要的是严格在当天之后的下一个交易日
            probe = date + pd.Timedelta(days=1)
            session = cal.date_to_session(
                probe.strftime("%Y-%m-%d"), direction="next"
            )
            return pd.Timestamp(session, tz=date.tz)
        except Exception as e:
            logger.warning("next_trading_day fail-open: %s", e)
            return date + pd.Timedelta(days=1)

    def prev_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        self._ensure_aware(date)
        cal = self._calendar()
        if cal is None:
            return date - pd.Timedelta(days=1)
        try:
            # 严格在当天之前的上一个交易日
            probe = date - pd.Timedelta(days=1)
            session = cal.date_to_session(
                probe.strftime("%Y-%m-%d"), direction="previous"
            )
            return pd.Timestamp(session, tz=date.tz)
        except Exception as e:
            logger.warning("prev_trading_day fail-open: %s", e)
            return date - pd.Timedelta(days=1)
