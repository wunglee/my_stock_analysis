"""交易日历适配器

将 exchange-calendars 封装为 ITradingCalendar 接口实现。

===== 设计决策：日历异常永不静默吞掉 =====

本模块的底线原则：当日历操作失败时，**绝不**回退到自然日列表（含周末）。
这不是"防御性编程"，这是在隐藏 bug。

历史上发生过 DateOutOfBounds 被 except Exception 吞掉，导致回退到自然日列表，
周末被标记为"缺失交易日"，触发全量 7 数据源链式拉取（66s+）的恶性 bug。
根本原因是 fail-open 掩盖了日历越界的事实，让错误一层层放大。

规则：
- cal is None（无法加载日历）：抛出 RuntimeError，调用方必须处理
- DateOutOfBounds（请求日期超出日历覆盖范围）：clamp 到有效范围，这是**已知边界条件**，不是 bug
- 其他异常：原样传播，不做任何兜底。如果有 bug，让它暴露出来
- is_trading_day 对越界日期返回 False（超出日历范围 = 不可能是交易日）
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

try:
    import exchange_calendars as xcals

    _XCALS_AVAILABLE = True
except ImportError:
    _XCALS_AVAILABLE = False

logger = logging.getLogger(__name__)

_MARKET_EXCHANGE = {"cn": "XSHG", "hk": "XHKG", "us": "XNYS"}
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
        return self._tz

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_aware(self, ts: pd.Timestamp) -> pd.Timestamp:
        if ts.tz is None:
            raise ValueError(f"Timestamp must be timezone-aware, got naive: {ts}")
        return ts

    def _calendar(self):
        """加载 exchange_calendars 日历实例。

        注意：exchange_calendars 未安装或日历代码未知时**不吞异常**，
        由各调用方法决定如何处理（抛 RuntimeError 或按边界条件处理）。
        """
        if not _XCALS_AVAILABLE or not self._exchange:
            return None
        try:
            return xcals.get_calendar(self._exchange)
        except Exception as e:
            logger.warning("Failed to load calendar for %s: %s", self._market, e)
            return None

    def _is_date_oob(self, e: Exception) -> bool:
        """检测异常是否为 DateOutOfBounds（请求日期超出日历覆盖范围）。

        DateOutOfBounds 是已知的边界条件，不是程序 bug。
        例如 XSHG 日历第一条是 2006-05-12，请求更早的日期会触发此异常。
        """
        if not _XCALS_AVAILABLE:
            return False
        try:
            from exchange_calendars.errors import DateOutOfBounds
        except ImportError:
            return False
        return isinstance(e, DateOutOfBounds)

    # ------------------------------------------------------------------ #
    # ITradingCalendar implementation
    # ------------------------------------------------------------------ #
    def is_trading_day(self, date: pd.Timestamp) -> bool:
        """判断给定日期是否为交易日。

        日历加载失败 → 抛 RuntimeError（不允许静默假定是/否交易日）。
        DateOutOfBounds → 返回 False（超出日历范围的日期不可能是交易日）。
        """
        self._ensure_aware(date)
        cal = self._calendar()
        if cal is None:
            raise RuntimeError(
                f"无法加载交易日历 {self._exchange}，无法判断 {date.date()} 是否为交易日"
            )
        try:
            session = datetime(date.year, date.month, date.day)
            return cal.is_session(session)
        except Exception as e:
            if self._is_date_oob(e):
                return False
            raise  # 未知异常必须传播，不允许静默假定

    def trading_days_between(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        """返回 start~end 区间内的交易日列表。

        日历加载失败 → 抛 RuntimeError。
        DateOutOfBounds → clamp 到日历有效范围（这是已知边界条件）。
        其他异常 → 原样传播。
        """
        self._ensure_aware(start)
        self._ensure_aware(end)
        cal = self._calendar()
        if cal is None:
            raise RuntimeError(
                f"无法加载交易日历 {self._exchange}，无法计算 {start.date()}~{end.date()} 的交易日列表"
            )

        try:
            return self._sessions_in_range(cal, start, end)
        except Exception as e:
            if self._is_date_oob(e):
                first = pd.Timestamp(cal.first_session, tz=start.tz)
                last = pd.Timestamp(cal.last_session, tz=start.tz)
                clamped_start = max(start, first)
                clamped_end = min(end, last)
                if clamped_start > clamped_end:
                    return []
                logger.debug(
                    "trading_days_between clamped: %s~%s -> %s~%s",
                    start.strftime("%Y-%m-%d"),
                    end.strftime("%Y-%m-%d"),
                    clamped_start.strftime("%Y-%m-%d"),
                    clamped_end.strftime("%Y-%m-%d"),
                )
                return self._sessions_in_range(cal, clamped_start, clamped_end)
            raise  # 不是 DateOutOfBounds — 这是真的 bug，必须暴露

    def _sessions_in_range(self, cal, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
        sessions = cal.sessions_in_range(
            start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
        return [pd.Timestamp(s, tz=start.tz) for s in sessions]

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        """返回 date 之后的下一个交易日。

        日历加载失败 → 抛 RuntimeError。
        DateOutOfBounds → 返回日历最早有效日（date 在日历开始之前时）或 date + 1 天。
        """
        self._ensure_aware(date)
        cal = self._calendar()
        if cal is None:
            raise RuntimeError(
                f"无法加载交易日历 {self._exchange}，无法计算 {date.date()} 的下一个交易日"
            )
        try:
            probe = date + pd.Timedelta(days=1)
            session = cal.date_to_session(
                probe.strftime("%Y-%m-%d"), direction="next"
            )
            return pd.Timestamp(session, tz=date.tz)
        except Exception as e:
            if self._is_date_oob(e):
                first = pd.Timestamp(cal.first_session, tz=date.tz)
                if date < first:
                    return first
                return date + pd.Timedelta(days=1)
            raise

    def get_effective_trading_date(self, symbol: str) -> pd.Timestamp:
        """根据当前市场的盘前/盘后状态，计算最近一个有效收盘日。

        逻辑链路：股票代码 → 目标市场 → 盘前/盘后状态 → 最近收盘日

        1. 股票代码 → detect_market() 推断目标市场（cn/hk/us）
        2. 目标市场 → MarketTimeUtils 获取当前市场时间 + 交易时段状态
        3. 盘后（AFTER_CLOSE）+ 今天是交易日 → 返回今天
        4. 否则（盘前/交易中/午休/非交易日）→ 返回上一个交易日

        这是回测数据获取的 end_date 上限：请求超过此日期的数据毫无意义，
        只会触发外部数据源链式超时（如 Efinance 6-7s），拖慢整个请求。

        Raises:
            RuntimeError: 日历不可用时（不允许静默回退到自然日）
        """
        from src.chart_legacy.market_enums import MarketCode, TradingPhase
        from src.chart_legacy.market_time_utils import MarketTimeUtils
        from src.market_context import detect_market

        now = MarketTimeUtils.get_market_time_now(symbol)
        market_str = detect_market(symbol)  # 'cn', 'hk', 'us'
        market_code = MarketCode.parse(market_str.upper())  # MarketCode.CN/HK/US
        phase = MarketTimeUtils.determine_trading_phase(market_code, now)

        today = now.normalize()

        if phase == TradingPhase.AFTER_CLOSE:
            if self.is_trading_day(today):
                return today
            return self.prev_trading_day(today)

        return self.prev_trading_day(today)

    def prev_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        """返回 date 之前的上一个交易日。

        日历加载失败 → 抛 RuntimeError。
        DateOutOfBounds → 返回日历最后有效日（date 在日历结束之后时）或 date - 1 天。
        """
        self._ensure_aware(date)
        cal = self._calendar()
        if cal is None:
            raise RuntimeError(
                f"无法加载交易日历 {self._exchange}，无法计算 {date.date()} 的上一个交易日"
            )
        try:
            probe = date - pd.Timedelta(days=1)
            session = cal.date_to_session(
                probe.strftime("%Y-%m-%d"), direction="previous"
            )
            return pd.Timestamp(session, tz=date.tz)
        except Exception as e:
            if self._is_date_oob(e):
                last = pd.Timestamp(cal.last_session, tz=date.tz)
                if date > last:
                    return last
                return date - pd.Timedelta(days=1)
            raise
