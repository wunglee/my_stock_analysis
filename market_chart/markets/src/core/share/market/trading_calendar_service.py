"""
交易日历服务

职责：
1. 基于 pandas_market_calendars 提供多市场交易日历
2. 判断指定日期是否为交易日
3. 计算两个日期之间的交易日数
4. 判断两个日期是否为连续交易日

支持市场：
- CN (中国A股)
- US (美国股市)
- HK (香港股市)
- JP (日本股市)
- EU (欧洲股市)
- SG (新加坡股市)
"""

import logging
from typing import Optional, List

import pandas as pd
import pandas_market_calendars as mcal
from core.share.market.market_enums import MarketCode
from core.share.market.market_time_utils import MarketTimeUtils

logger = logging.getLogger(__name__)

class TradingCalendarService:
    """交易日历服务"""

    # 市场代码映射到 pandas_market_calendars 的交易所代码
    MARKET_CALENDAR_MAP = {
        MarketCode.CN: 'SSE',  # 上海证券交易所 (Shanghai Stock Exchange)
        MarketCode.US: 'NYSE',  # 纽约证券交易所 (New York Stock Exchange)
        MarketCode.HK: 'HKEX',  # 香港交易所 (Hong Kong Stock Exchange)
        MarketCode.JP: 'JPX',  # 日本交易所集团 (Japan Exchange Group)
        MarketCode.EU: 'LSE',  # 伦敦证券交易所 (London Stock Exchange) 代表欧洲
        MarketCode.SG: 'XSES',  # 新加坡交易所 (Singapore Exchange)
    }

    def __init__(self):
        """初始化交易日历服务"""
        self._calendars = {}
        self._cache = {}  # 缓存交易日判断结果

        if not mcal or mcal is False:
            raise RuntimeError("pandas_market_calendars 未安装，交易日历服务不可用")
        logger.info("✅ 交易日历服务初始化: 使用 pandas_market_calendars")

    def _get_calendar(self, market_code: MarketCode):
        """获取指定市场的交易日历

        Args:
            market_code: 市场代码枚举或字符串 (MarketCode.CN 或 'CN')

        Returns:
            交易日历对象

        Raises:
            RuntimeError: 如果日历加载失败
        """
        # 支持 MarketCode 枚举和字符串
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")

        if market_code not in self._calendars:
            exchange_code = self.MARKET_CALENDAR_MAP.get(market_code)

            if not exchange_code:
                raise RuntimeError(f"未知市场代码: {market_code}，无对应交易所日历")

            try:
                calendar = mcal.get_calendar(exchange_code)
                self._calendars[market_code] = calendar
                logger.debug(f"加载交易日历: {market_code} -> {exchange_code}")
            except Exception as e:
                logger.error(f"加载交易日历失败 ({market_code}, exchange={exchange_code}): {e}")
                raise RuntimeError(f"加载交易日历失败 ({market_code}): {e}") from e

        return self._calendars[market_code]

    def is_trading_day(self, market_code: MarketCode, date: pd.Timestamp) -> bool:
        """
        判断指定日期是否为交易日
        
        Args:
            market_code: 市场代码枚举或字符串 (MarketCode.CN 或 'CN')
            date: 日期 (pd.Timestamp)
        
        Returns:
            bool: True表示是交易日，False表示非交易日
        
        Examples:
            >>> service = TradingCalendarService()
            >>> service.is_trading_day(MarketCode.CN, pd.Timestamp(2024, 10, 1))  # 国庆节
            False
            >>> service.is_trading_day(MarketCode.CN, pd.Timestamp('2024-10-08'))  # 工作日
            True
        """
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")
        if not isinstance(date, pd.Timestamp):
            raise TypeError("date must be pd.Timestamp")

        # 确保日期包含市场时区，这将基于市场时区确定日期
        date_with_market_tz = MarketTimeUtils.to_market_time(date, market_code)
        
        # 获取市场时区下的日期部分，保留时区信息
        market_date = date_with_market_tz.normalize()

        # 缓存键 - 使用市场时区下的日期
        cache_key = f"{market_code}_{market_date.strftime('%Y-%m-%d')}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 使用交易日历
        calendar = self._get_calendar(market_code)

        # 获取该日期所在月份的交易日
        year = market_date.year
        month = market_date.month
        schedule = calendar.schedule(
            start_date=f'{year}-{month:02d}-01',
            end_date=f'{year}-{month:02d}-{pd.Timestamp(year, month, 1).days_in_month}'
        )

        # 将日历返回的naive日期转换为带市场时区的日期进行比较
        market_date_naive = market_date.tz_localize(None)
        result = market_date_naive in schedule.index

        self._cache[cache_key] = result
        return result

    def get_trading_days_between(self, market_code: MarketCode,
                                 start_date: pd.Timestamp,
                                 end_date: pd.Timestamp) -> List[pd.Timestamp]:
        """
        获取两个日期之间的所有交易日
        
        Args:
            market_code: 市场代码枚举或字符串
            start_date: 起始日期（包含）(pd.Timestamp)
            end_date: 结束日期（包含）(支持 pd.Timestamp)
        
        Returns:
            交易日列表 (pd.Timestamp 类型)
        
        Examples:
            >>> service = TradingCalendarService()
            >>> days = service.get_trading_days_between(MarketCode.CN, 
            ...     pd.Timestamp('2024-09-30'), pd.Timestamp('2024-10-08'))
            >>> len(days)  # 跳过国庆假期
            2  # 9月30日 和 10月8日
        """
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")
        if not isinstance(end_date, pd.Timestamp):
            raise TypeError("end_date must be pd.Timestamp")
        if not isinstance(start_date, pd.Timestamp):
            raise TypeError("start_date must be pd.Timestamp")
        
        # 确保日期包含市场时区，获取市场时区下的日期
        start_date_with_tz = MarketTimeUtils.to_market_time(start_date, market_code)
        end_date_with_tz = MarketTimeUtils.to_market_time(end_date, market_code)
        
        start_market_date = start_date_with_tz.normalize()
        end_market_date = end_date_with_tz.normalize()

        # 使用交易日历
        calendar = self._get_calendar(market_code)

        # 将带时区的日期转换为naive日期以与日历库交互
        start_date_naive = start_market_date.tz_localize(None)
        end_date_naive = end_market_date.tz_localize(None)
        
        schedule = calendar.schedule(
            start_date=start_date_naive.strftime('%Y-%m-%d'),
            end_date=end_date_naive.strftime('%Y-%m-%d')
        )

        # 转换为带时区的 pd.Timestamp 列表
        timezone = MarketTimeUtils.get_market_timezone(market_code)
        trading_days = [dt.tz_localize(timezone) for dt in schedule.index]
        return trading_days

    def is_consecutive_trading_days(self, market_code: MarketCode,
                                    date1: pd.Timestamp,
                                    date2: pd.Timestamp) -> bool:
        """
        判断两个日期是否为连续交易日（中间没有其他交易日）
        
        Args:
            market_code: 市场代码枚举或字符串
            date1: 第一个日期（应早于date2）(支持 pd.Timestamp)
            date2: 第二个日期 (支持 pd.Timestamp)
        
        Returns:
            bool: True表示连续，False表示不连续
        
        Examples:
            >>> service = TradingCalendarService()
            >>> # 周五 -> 下周一（连续）
            >>> service.is_consecutive_trading_days(MarketCode.CN,
            ...     pd.Timestamp('2024-01-05'), pd.Timestamp('2024-01-08'))
            True
            >>> # 国庆前 -> 国庆后（不连续，中间有假期）
            >>> service.is_consecutive_trading_days(MarketCode.CN,
            ...     pd.Timestamp('2024-09-30'), pd.Timestamp('2024-10-08'))
            True  # 实际上是连续的（因为中间都是假期）
        """
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")
        if not isinstance(date1, pd.Timestamp):
            raise TypeError("date1 must be pd.Timestamp")
        if not isinstance(date2, pd.Timestamp):
            raise TypeError("date2 must be pd.Timestamp")

        # 确保日期包含市场时区，获取市场时区下的日期
        date1_with_tz = MarketTimeUtils.to_market_time(date1, market_code)
        date2_with_tz = MarketTimeUtils.to_market_time(date2, market_code)
        
        date1_market_date = date1_with_tz.normalize()
        date2_market_date = date2_with_tz.normalize()

        if date1_market_date >= date2_market_date:
            return False

        # 获取两个日期之间的所有交易日
        trading_days = self.get_trading_days_between(market_code, date1, date2)

        # 连续交易日：只有date1和date2两个交易日，并且它们是实际的交易日
        if len(trading_days) == 2:
            # 将输入日期转换为日期部分进行比较，确保它们是实际的交易日
            # 使用带时区日期的日期部分进行比较
            date1_date_part = date1_market_date.tz_localize(None).date()
            date2_date_part = date2_market_date.tz_localize(None).date()
            day1_date_part = trading_days[0].normalize().tz_localize(None).date()
            day2_date_part = trading_days[1].normalize().tz_localize(None).date()
            
            # 检查这两个交易日是否对应于输入的日期（按日期部分匹配）
            # 并确保顺序正确（第一个交易日对应date1，第二个对应date2）
            if (day1_date_part == date1_date_part and 
                day2_date_part == date2_date_part and
                day1_date_part <= day2_date_part):
                return True

        return False

    def get_next_trading_day(self, market_code: MarketCode,
                             date: pd.Timestamp) -> Optional[pd.Timestamp]:
        """
        获取下一个交易日
        
        Args:
            market_code: 市场代码枚举或字符串
            date: 当前日期 (支持 pd.Timestamp)
        
        Returns:
            下一个交易日 (pd.Timestamp)，如果未来30天内没有则返回None
        """
        # 统一转换为 pd.Timestamp 类型
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")
        if not isinstance(date, pd.Timestamp):
            raise TypeError("date must be pd.Timestamp")

        # 确保日期包含市场时区
        date_with_tz = MarketTimeUtils.to_market_time(date, market_code)

        # 搜索未来30天，基于市场时区的日期
        search_date_with_tz = (date_with_tz + pd.Timedelta(days=1)).tz_convert(MarketTimeUtils.get_market_timezone(market_code))
        end_date_with_tz = (date_with_tz + pd.Timedelta(days=30)).tz_convert(MarketTimeUtils.get_market_timezone(market_code))
        
        trading_days = self.get_trading_days_between(market_code, search_date_with_tz, end_date_with_tz)

        if trading_days:
            # 返回的第一个交易日应该带有市场时区
            next_day = trading_days[0]
            timezone = MarketTimeUtils.get_market_timezone(market_code)
            if next_day.tzinfo is None:
                next_day = next_day.tz_localize(timezone)
            else:
                next_day = next_day.tz_convert(timezone)
            return next_day
        return None

    def get_previous_trading_day(self, market_code: MarketCode,
                                 date: pd.Timestamp) -> Optional[pd.Timestamp]:
        """
        获取上一个交易日
        
        Args:
            market_code: 市场代码枚举或字符串
            date: 当前日期 (支持 pd.Timestamp)
        
        Returns:
            上一个交易日 (pd.Timestamp)，如果过去30天内没有则返回None
        """
        # 统一转换为 pd.Timestamp 类型
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")
        if not isinstance(date, pd.Timestamp):
            raise TypeError("date must be pd.Timestamp")

        # 确保日期包含市场时区
        date_with_tz = MarketTimeUtils.to_market_time(date, market_code)

        # 搜索过去30天，基于市场时区的日期
        start_date_with_tz = (date_with_tz - pd.Timedelta(days=30)).tz_convert(MarketTimeUtils.get_market_timezone(market_code))
        search_date_with_tz = (date_with_tz - pd.Timedelta(days=1)).tz_convert(MarketTimeUtils.get_market_timezone(market_code))
        
        trading_days = self.get_trading_days_between(market_code, start_date_with_tz, search_date_with_tz)

        if trading_days:
            # 返回的最后一个交易日应该带有市场时区
            prev_day = trading_days[-1]
            timezone = MarketTimeUtils.get_market_timezone(market_code)
            if prev_day.tzinfo is None:
                prev_day = prev_day.tz_localize(timezone)
            else:
                prev_day = prev_day.tz_convert(timezone)
            return prev_day
        return None

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("交易日历缓存已清空")


# 全局单例
_service_instance = None


def get_trading_calendar_service() -> TradingCalendarService:
    """获取交易日历服务单例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = TradingCalendarService()
    return _service_instance