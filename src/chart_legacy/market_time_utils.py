"""市场时间工具 - 简化版

从 market_chart/markets/src/core/share/market/market_time_utils.py 改编
只保留 chart_data_assembler 需要的方法，移除深层依赖。
"""

import logging
import pandas as pd

from src.chart_legacy.market_enums import MarketCode

logger = logging.getLogger(__name__)

# 简化的市场时区映射
_MARKET_TIMEZONES = {
    'CN': 'Asia/Shanghai',
    'US': 'America/New_York',
    'HK': 'Asia/Hong_Kong',
    'JP': 'Asia/Tokyo',
    'EU': 'Europe/London',
    'SG': 'Asia/Singapore',
}


def _detect_market(symbol: str) -> str:
    """从股票代码推断市场（返回大写代码，兼容 _MARKET_TIMEZONES）"""
    from src.market_context import detect_market
    return detect_market(symbol).upper()


class MarketTimeUtils:
    """市场时间工具 - 简化版"""

    @staticmethod
    def get_market_timezone_from_symbol(symbol: str):
        market = _detect_market(symbol)
        tz_str = _MARKET_TIMEZONES.get(market, 'UTC')
        return pd.Timestamp.now(tz=tz_str).tz

    @staticmethod
    def get_market_timezone(market: MarketCode):
        tz_str = _MARKET_TIMEZONES.get(market.value, 'UTC')
        return pd.Timestamp.now(tz=tz_str).tz

    @staticmethod
    def get_market_time_now(symbol: str) -> pd.Timestamp:
        """获取指定 symbol 所属市场的当前本地时间（带时区）"""
        market = _detect_market(symbol)
        tz_str = _MARKET_TIMEZONES.get(market, 'UTC')
        return pd.Timestamp.now(tz=tz_str)

    @staticmethod
    def determine_trading_phase(market: MarketCode, market_local_time: pd.Timestamp):
        """判断市场交易时段

        逻辑：
        1. 通过交易日历判断今天是否为交易日（非交易日 → AFTER_CLOSE）
        2. 交易日才判断具体时段（盘前、盘中、午休、盘后）
        """
        from datetime import time as dt_time
        from src.chart_legacy.market_enums import TradingPhase

        if market_local_time.tzinfo is None:
            return TradingPhase.AFTER_CLOSE

        # 步骤1：判断是否为交易日
        market_tz = MarketTimeUtils.get_market_timezone(market)
        market_date_ts = pd.Timestamp(market_local_time.date()).tz_localize(market_tz)

        try:
            from src.data_provider.trading_calendar_adapter import XCalTradingCalendar
            calendar = XCalTradingCalendar(market=market.value.lower())
            if not calendar.is_trading_day(market_date_ts):
                return TradingPhase.AFTER_CLOSE
        except Exception:
            # 日历异常时 fallback：周末直接判定为非交易
            weekday = market_local_time.weekday()
            if weekday >= 5:
                return TradingPhase.AFTER_CLOSE
            # 工作日继续走时间判断（可能包含节假日误报，但比静默失败好）

        # 步骤2：判断具体时段
        current_time = market_local_time.time()

        # A股交易时间 09:30-11:30, 13:00-15:00
        if market.value == 'CN':
            if dt_time(9, 30) <= current_time <= dt_time(11, 30):
                return TradingPhase.TRADING
            if dt_time(13, 0) <= current_time <= dt_time(15, 0):
                return TradingPhase.TRADING
            if dt_time(9, 0) <= current_time < dt_time(9, 30):
                return TradingPhase.BEFORE_OPEN
            return TradingPhase.AFTER_CLOSE

        # 美股 09:30-16:00
        if market.value == 'US':
            if dt_time(9, 30) <= current_time <= dt_time(16, 0):
                return TradingPhase.TRADING
            return TradingPhase.AFTER_CLOSE

        return TradingPhase.AFTER_CLOSE

    @staticmethod
    def to_market_time(date_time: pd.Timestamp, market_code: MarketCode) -> pd.Timestamp:
        """确保时间戳带有正确的市场时区"""
        market_tz = MarketTimeUtils.get_market_timezone(market_code)
        if date_time.tz is None:
            return date_time.tz_localize(market_tz)
        return date_time.tz_convert(market_tz)

    @staticmethod
    def get_last_trade_date_for_symbol(symbol: str, market_local_time: pd.Timestamp) -> pd.Timestamp:
        """通过 symbol 获取最后一个交易日（便捷方法）"""
        market = _detect_market(symbol)
        market_code = MarketCode.parse(market)
        return MarketTimeUtils.get_last_trade_date(market_code, market_local_time)

    @staticmethod
    def to_market_time_by_symbol(date_time: pd.Timestamp, symbol: str) -> pd.Timestamp:
        """确保时间戳带有正确的市场时区（通过 symbol 推断）"""
        market = _detect_market(symbol)
        market_code = MarketCode.parse(market)
        return MarketTimeUtils.to_market_time(date_time, market_code)

    @staticmethod
    def get_last_trade_date(market: MarketCode, market_local_time: pd.Timestamp) -> pd.Timestamp:
        """返回最后一个完整交易日（用于历史K线查询的上界）

        规则：
        - 盘前 → 前一工作日
        - 盘中/午盘/盘后：若今天是工作日 → 今天，否则 → 前一工作日
        """
        from src.chart_legacy.market_enums import TradingPhase

        if market_local_time.tzinfo is None:
            market_local_time = MarketTimeUtils.to_market_time(market_local_time, market)
        date = market_local_time.normalize()
        trading_phase = MarketTimeUtils.determine_trading_phase(market, market_local_time)

        if trading_phase == TradingPhase.BEFORE_OPEN:
            weekday = date.weekday()
            if weekday == 0:
                return date - pd.Timedelta(days=3)
            elif weekday == 6:
                return date - pd.Timedelta(days=2)
            return date - pd.Timedelta(days=1)

        weekday = date.weekday()
        if weekday == 5:
            return date - pd.Timedelta(days=1)
        elif weekday == 6:
            return date - pd.Timedelta(days=2)
        return date
