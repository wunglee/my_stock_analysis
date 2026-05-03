"""市场时间工具 - 简化版

从 temp/markets/src/core/share/market/market_time_utils.py 改编
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


def _infer_market_from_symbol(symbol: str) -> str:
    """从股票代码推断市场"""
    if not symbol:
        return 'CN'
    s = symbol.strip().upper()
    if s.endswith('.US') or (len(s) <= 5 and s.isalpha()):
        return 'US'
    if s.endswith('.HK') or (s.startswith('HK') and s[2:].isdigit()):
        return 'HK'
    if s.startswith('6') or s.startswith('0') or s.startswith('3') or s.startswith('8') or s.startswith('9'):
        return 'CN'
    if s.startswith('1') or s.startswith('2') or s.startswith('5'):
        return 'CN'  # 指数/基金
    return 'CN'


class MarketTimeUtils:
    """市场时间工具 - 简化版"""

    @staticmethod
    def get_market_timezone_from_symbol(symbol: str):
        market = _infer_market_from_symbol(symbol)
        tz_str = _MARKET_TIMEZONES.get(market, 'UTC')
        return pd.Timestamp.now(tz=tz_str).tz

    @staticmethod
    def get_market_timezone(market: MarketCode):
        tz_str = _MARKET_TIMEZONES.get(market.value, 'UTC')
        return pd.Timestamp.now(tz=tz_str).tz

    @staticmethod
    def get_market_time_now(symbol: str) -> pd.Timestamp:
        """获取指定 symbol 所属市场的当前本地时间（带时区）"""
        market = _infer_market_from_symbol(symbol)
        tz_str = _MARKET_TIMEZONES.get(market, 'UTC')
        return pd.Timestamp.now(tz=tz_str)

    @staticmethod
    def determine_trading_phase(market: MarketCode, market_local_time: pd.Timestamp):
        """简化版：只判断是否在交易时段"""
        from src.chart_legacy.market_enums import TradingPhase
        if market_local_time.tzinfo is None:
            return TradingPhase.AFTER_CLOSE
        current_time = market_local_time.time()
        # A股交易时间 09:30-11:30, 13:00-15:00
        if market.value == 'CN':
            from datetime import time as dt_time
            if dt_time(9, 30) <= current_time <= dt_time(11, 30):
                return TradingPhase.TRADING
            if dt_time(13, 0) <= current_time <= dt_time(15, 0):
                return TradingPhase.TRADING
            if dt_time(9, 0) <= current_time < dt_time(9, 30):
                return TradingPhase.BEFORE_OPEN
            return TradingPhase.AFTER_CLOSE
        # 美股 09:30-16:00
        if market.value == 'US':
            from datetime import time as dt_time
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
    def to_market_time_by_symbol(date_time: pd.Timestamp, symbol: str) -> pd.Timestamp:
        """确保时间戳带有正确的市场时区（通过 symbol 推断）"""
        market = _infer_market_from_symbol(symbol)
        market_code = MarketCode.parse(market)
        return MarketTimeUtils.to_market_time(date_time, market_code)

    @staticmethod
    def get_last_trade_date(market: MarketCode, market_local_time: pd.Timestamp) -> pd.Timestamp:
        """简化版：返回前一个工作日"""
        if market_local_time.tzinfo is None:
            market_local_time = MarketTimeUtils.to_market_time(market_local_time, market)
        date = market_local_time.normalize()
        weekday = date.weekday()
        if weekday == 0:  # 周一
            return date - pd.Timedelta(days=3)
        elif weekday == 6:  # 周日
            return date - pd.Timedelta(days=2)
        return date - pd.Timedelta(days=1)
