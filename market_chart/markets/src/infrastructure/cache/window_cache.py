"""
时间窗口管理器（重构版） - 基于 period 和 window_size 的窗口管理

核心概念：
- period（数据粒度）: daily/weekly/monthly，K线类型
- window_size（窗口大小）: 整数，表示包含多少个period单位
  例如：period=daily, window_size=7 → 7天一个窗口
       period=weekly, window_size=4 → 4周一个窗口
       period=monthly, window_size=3 → 3个月一个窗口

窗口键格式：
- daily窗口: YYYYMMDD_YYYYMMDD (起始日期_结束日期，例如：20250113_20250119)
- weekly窗口: YYYY-Www_Www (起始周_结束周，例如：2025-W02_W02 表示单周窗口)
- monthly窗口: YYYY-MM_MM (起始月_结束月，例如：2025-01_03 表示1-3月)

注意：
- 窗口边界对齐到period的自然边界
- daily: 自然日
- weekly: ISO周（周一到周日）
- monthly: 月初到月末
"""

import logging
from typing import List, Tuple, Optional, Dict
import pandas as pd

from core.share.market.market_enums import MarketCode
from core.share.market.market_time_utils import MarketTimeUtils
from core.share.market.trading_calendar_service import get_trading_calendar_service
from infrastructure.cache.memory import MemoryCache


logger = logging.getLogger('WindowManager')


class WindowsCache:
    """时间窗口管理工具类（重构版）"""

    def __init__(self):
        """初始化窗口管理器"""
        window_size = {"daily": 7, "weekly": 4, "monthly": 12}

        self._calendar_service = get_trading_calendar_service()
        self._fast_cache = MemoryCache(max_windows=1000)
        self._window_size: dict[str, int] = window_size
        logger.info(f"✅ WindowsCache 初始化完成: window_size={self._window_size}")

    def _make_window_key(self, date: pd.Timestamp, period: str) -> Optional[str]:
        """
        生成时间窗口键
        
        Args:
            date: 日期
            period: 数据粒度 (daily/weekly/monthly)
        
        Returns:
            窗口键字符串，如果窗口无效（调整后window_start > window_end）则返回None
        
        Examples:
            >>> self._make_window_key(pd.Timestamp('2025-01-15'), 'daily')
            '20250113_20250119'  # 2025-01-13 到 2025-01-19 (7天窗口，对齐到周一)
            
            >>> self._make_window_key(pd.Timestamp('2025-01-15'), 'weekly')
            '2025-W02_W05'  # 第2周到第5周 (4周窗口)
            
            >>> self._make_window_key(pd.Timestamp('2025-02-15'), 'monthly')
            '2025-01_03'  # 1月到3月 (3个月窗口)
        """
        date_no_tz = date.tz_localize(None)
        if not isinstance(date_no_tz, pd.Timestamp):
            raise TypeError("date must be pd.Timestamp")

        result = None
        if period == 'daily':
            window_size = self._window_size.get('daily')
            # Daily窗口：按window_size天一个窗口
            # 窗口边界按固定周期长度对齐，不考虑交易日历
            # 修复：使用一个固定基准日期（如公元1年1月1日）来计算天数，避免跨年问题
            base_date = pd.Timestamp('1970-01-01')# 使用Unix纪元作为基准
            days_from_base = (date_no_tz - base_date).days
            window_index = days_from_base // window_size

            # 计算窗口边界（从基准日期开始）
            window_start = base_date + pd.Timedelta(days=window_index * window_size)
            window_end = window_start + pd.Timedelta(days=window_size-1)

            result = f"{window_start.strftime('%Y%m%d')}_{window_end.strftime('%Y%m%d')}"

        elif period == 'weekly':
            window_size = self._window_size.get('weekly')
            # Weekly窗口：基于ISO周，window_size周一个窗口
            iso_year, iso_week, _ = date_no_tz.isocalendar()

            # 计算窗口索引（从第1周开始，每window_size周一个窗口）
            window_index = (iso_week - 1) // window_size
            start_week = window_index * window_size + 1
            
            # 计算窗口起始日期（该年第start_week周的周一）
            start_date = pd.to_datetime(f'{iso_year}-W{start_week:02d}-1', format='%G-W%V-%u')
            # 计算窗口结束日期（再window_size周后的周日）
            end_date = start_date + pd.Timedelta(weeks=window_size) - pd.Timedelta(days=1)
            
            # 获取结束日期的实际ISO周号
            end_year, end_week, _ = end_date.isocalendar()

            # 始终包含结束年份，保持格式一致
            result = f"{iso_year}-W{start_week:02d}_{end_year}-W{end_week:02d}"

        elif period == 'monthly':
            window_size = self._window_size.get('monthly')
            # Monthly窗口：基于月份，window_size月一个窗口
            # 计算窗口索引（从1月开始，每window_size月一个窗口）
            # 修复：使用年份和月份的组合来计算窗口索引
            total_months = (date_no_tz.year - 1970) * 12 + date_no_tz.month - 1  # 从基准年1970年开始计算月数
            window_index = total_months // window_size
            start_month_offset = window_index * window_size
            start_year = 1970 + start_month_offset // 12
            start_month = (start_month_offset % 12) + 1
            end_month_offset = start_month_offset + window_size - 1
            end_year = 1970 + end_month_offset // 12
            end_month = (end_month_offset % 12) + 1

            # 始终包含结束年份，保持格式一致
            result = f"{start_year}-{start_month:02d}_{end_year}-{end_month:02d}"

        else:
            raise ValueError(f"不支持的 period: {period}，必须是 'daily', 'weekly' 或 'monthly'")
        return result

    def _generate_window_keys(self, start: pd.Timestamp, end: pd.Timestamp, period: str,
                              market_code: Optional[MarketCode] = None) -> List[str]:
        """
        生成指定范围内的所有窗口键
        
        Args:
            start: 开始日期（YYYY-MM-DD）
            end: 结束日期（YYYY-MM-DD）
            period: 数据粒度 (daily/weekly/monthly)
            market_code:市场代码
        
        Returns:
            窗口键列表（去重且排序）
        
        Examples:
            >>> self._generate_window_keys(pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'), 'weekly')
            ['2025-W01_W01', '2025-W02_W02', '2025-W03_W03', '2025-W04_W04', '2025-W05_W05']
            
            >>> self._generate_window_keys(pd.Timestamp('2025-01-01'), pd.Timestamp('2025-03-31'), 'monthly')
            ['2025-01_03']
        """
        if not isinstance(market_code, MarketCode):
            raise TypeError("market_code must be MarketCode")
        if not isinstance(start, pd.Timestamp):
            raise TypeError("start must be pd.Timestamp")
        if not isinstance(end, pd.Timestamp):
            raise TypeError("end must be pd.Timestamp")
        start_no_tz=start.tz_localize(None)
        end_no_tz=end.tz_localize(None)
        if start_no_tz > end_no_tz:
            return []

        # 生成连续的窗口键，确保窗口之间连续且不重叠
        window_keys = []
        
        # 从起始日期开始生成第一个窗口
        current_date = start_no_tz
        while current_date <= end_no_tz:
            # 为当前日期生成窗口
            window_key = self._make_window_key(current_date, period)
            if window_key is None:
                # 如果无法生成窗口，跳到下一天继续尝试
                current_date += pd.Timedelta(days=1)
                continue
            
            # 检查窗口是否已经在结果中（防止重复）
            if window_key not in window_keys:
                # 添加窗口键
                window_keys.append(window_key)
            # 获取当前窗口的结束日期
            _, window_end = self._window_key_to_date_range(window_key, period)
            
            # 如果当前窗口的结束日期已经超过了总的结束日期，则结束循环
            if window_end >= end_no_tz:
                break
            
            # 从当前窗口的结束日期的下一天开始
            current_date = window_end + pd.Timedelta(days=1)

        logger.info(f"📦 需要 {len(window_keys)} 个窗口 (period={period}, window_size={self._window_size.get(period)})")
        return sorted(list(set(window_keys)))  # 去重并排序

    @staticmethod
    def _window_key_to_date_range(window_key: str, period: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """
        将窗口键转换为日期范围
        
        Args:
            window_key: 窗口键
            period: 数据粒度 (daily/weekly/monthly)
        
        Returns:
            (start_date, end_date) 元组，格式为 YYYY-MM-DD
        
        Examples:
            >>> WindowsCache._window_key_to_date_range('20250113_20250119', 'daily')
            ('2025-01-13', '2025-01-19')
            
            >>> WindowsCache._window_key_to_date_range('2025-W02_W05', 'weekly')
            ('2025-01-06', '2025-02-02')  # 第2周周一到第5周周日
            
            >>> WindowsCache._window_key_to_date_range('2025-01_03', 'monthly')
            ('2025-01-01', '2025-03-31')
        """
        if period == 'daily':
            # Daily窗口格式: YYYYMMDD_YYYYMMDD
            start_str, end_str = window_key.split('_')
            start_date = pd.to_datetime(start_str, format='%Y%m%d')
            end_date = pd.to_datetime(end_str, format='%Y%m%d')

        elif period == 'weekly':
            # Weekly窗口格式: YYYY-Www_YYYY-Www (始终包含结束年份)
            parts = window_key.split('_')
            year_week_start = parts[0]  # YYYY-Www
            year_week_end = parts[1]  # YYYY-Www

            # 解析起始周
            year_start, week_start = year_week_start.split('-W')
            year_start = int(year_start)
            week_start = int(week_start)

            # 解析结束周
            year_end, week_end = year_week_end.split('-W')
            year_end = int(year_end)
            week_end = int(week_end)

            # 计算起始周的周一
            start_date = pd.to_datetime(f'{year_start}-W{week_start:02d}-1', format='%G-W%V-%u')

            # 计算结束周的周日
            end_date = pd.to_datetime(f'{year_end}-W{week_end:02d}-7', format='%G-W%V-%u')

        elif period == 'monthly':
            # Monthly窗口格式: YYYY-MM_YYYY-MM (始终包含结束年份)
            parts = window_key.split('_')
            year_month_start = parts[0]  # YYYY-MM
            year_month_end = parts[1]  # YYYY-MM

            # 解析起始月
            year_start, start_month = year_month_start.split('-')
            year_start = int(year_start)
            start_month = int(start_month)

            # 解析结束月
            year_end, end_month = year_month_end.split('-')
            year_end = int(year_end)
            end_month = int(end_month)

            # 起始月第一天
            start_date = pd.Timestamp(year=year_start, month=start_month, day=1)

            # 结束月最后一天
            if end_month == 12:
                end_date = pd.Timestamp(year=year_end + 1, month=1, day=1) - pd.Timedelta(days=1)
            else:
                end_date = pd.Timestamp(year=year_end, month=end_month + 1, day=1) - pd.Timedelta(days=1)
        else:
            raise ValueError(f"不支持的 period: {period}")
        return start_date, end_date

    @staticmethod
    def is_date_in_window(window_key: str, period: str, date: pd.Timestamp) -> bool:
        """
        判断窗口是否为当前未完成窗口

        Args:
            window_key: 窗口键
            period: 数据粒度
            date: 当前日期

        Returns:
            True 如果是当前未完成窗口
        """
        start_str, end_str = WindowsCache._window_key_to_date_range(window_key, period)
        start_date = pd.to_datetime(start_str)
        end_date = pd.to_datetime(end_str)
        date_no_tz= date.tz_localize(None)
        # 当前日期在窗口范围内，且窗口尚未结束
        return start_date <= date_no_tz <= end_date

    def merge_continuous_windows(self, window_keys: list, period: str) -> list:
        """
        合并连续的窗口键，减少网络请求次数

        Args:
            window_keys: 缺失窗口键列表 (已排序)
            period: 数据粒度

        Returns:
            合并后的连续范围列表，每个元素包含:
            - start: 范围起始日期
            - end: 范围结束日期
            - windows: 该范围包含的窗口键列表

        Example:
            Input: ['2024-01_01', '2024-02_02', '2024-03_03', '2024-05_05', '2024-06_06']
            Output: [
                {'start': '2024-01-01', 'end': '2024-03-31', 'windows': ['2024-01_01', '2024-02_02', '2024-03_03']},
                {'start': '2024-05-01', 'end': '2024-06-30', 'windows': ['2024-05_05', '2024-06_06']}
            ]
        """
        if not window_keys:
            return []

        # 按窗口键排序
        sorted_keys = sorted(window_keys)

        merged_ranges = []
        current_range_windows = [sorted_keys[0]]

        for i in range(1, len(sorted_keys)):
            prev_key = sorted_keys[i - 1]
            curr_key = sorted_keys[i]

            # 检查是否连续：下一个窗口紧跟上一个窗口
            if self.is_consecutive_windows(prev_key, curr_key, period):
                # 连续，加入当前范围
                current_range_windows.append(curr_key)
            else:
                # 不连续，保存当前范围，开始新范围
                range_start, _ = self._window_key_to_date_range(current_range_windows[0], period)
                _, range_end = self._window_key_to_date_range(current_range_windows[-1], period)
                merged_ranges.append({
                    'start': range_start,  # 已经是 pd.Timestamp 类型
                    'end': range_end,  # 已经是 pd.Timestamp 类型
                    'windows': current_range_windows.copy()
                })
                current_range_windows = [curr_key]

        # 添加最后一个范围
        range_start, _ = self._window_key_to_date_range(current_range_windows[0], period)
        _, range_end = self._window_key_to_date_range(current_range_windows[-1], period)
        merged_ranges.append({
            'start': range_start,  # 已经是 pd.Timestamp 类型，无需再次包装
            'end': range_end,      # 已经是 pd.Timestamp 类型，无需再次包装
            'windows': current_range_windows.copy()
        })

        return merged_ranges

    def is_consecutive_windows(self, key1: str, key2: str, period: str) -> bool:
        """
        判断两个窗口是否连续（基于不同周期的判断逻辑）

        Args:
            key1: 第一个窗口键
            key2: 第二个窗口键
            period: 数据粒度 (daily/weekly/monthly)

        Returns:
            True 表示连续，False 表示不连续

        逻辑：
            - daily: 判断日期是否连续（简单日期连续性）
            - weekly: 判断ISO周号是否连续
            - monthly: 判断月份是否连续
        """

        if period == 'daily':
            # Daily周期：判断日期范围是否连续
            # 获取两个窗口的日期范围
            _, end1 = self._window_key_to_date_range(key1, period)
            start2, _ = self._window_key_to_date_range(key2, period)

            # 转换为pd.Timestamp对象
            end1_dt = pd.to_datetime(end1)
            start2_dt = pd.to_datetime(start2)

            # 简单判断：第一个窗口的结束日期 + 1天 = 第二个窗口的开始日期
            return end1_dt + pd.Timedelta(days=1) == start2_dt

        elif period == 'weekly':
            # Weekly周期：判断ISO周号是否连续
            # 窗口键格式：YYYY-Www_YYYY-Www（例如：2020-W52_2020-W52, 2020-W53_2021-W53）
            # 注意：2020-W53_2021-W53 表示 2020年第53周，结束日落在 2021年
            try:
                # 解析起始周和结束周的日期，然后计算 ISO 周号
                parts1 = key1.split('_')
                year1_week_start = parts1[0]  # YYYY-Www (起始周)
                year1_week_end = parts1[1]  # YYYY-Www (结束周)

                parts2 = key2.split('_')
                year2_week_start = parts2[0]  # YYYY-Www (起始周)

                # 计算 key1 的结束周的实际 ISO 周号
                year1_end, week1_end = year1_week_end.split('-W')
                end1_date = pd.to_datetime(f'{year1_end}-W{week1_end}-7', format='%G-W%V-%u')
                end1_iso_year, end1_iso_week, _ = end1_date.isocalendar()

                # 计算 key2 的起始周的实际 ISO 周号
                year2_start, week2_start = year2_week_start.split('-W')
                start2_date = pd.to_datetime(f'{year2_start}-W{week2_start}-1', format='%G-W%V-%u')
                start2_iso_year, start2_iso_week, _ = start2_date.isocalendar()

                # 判断连续性：比较 ISO 年份和 ISO 周号
                if end1_iso_year == start2_iso_year:
                    # 同一年：周号连续
                    return (end1_iso_week + 1) == start2_iso_week
                elif end1_iso_year + 1 == start2_iso_year:
                    # 跨年：第53周 → 第1周
                    return end1_iso_week >= 52 and start2_iso_week == 1
                else:
                    return False
            except (ValueError, IndexError) as e:
                logger.warning(f"⚠️ 解析周窗口键失败: {key1}, {key2}, error: {e}")
                return False

        elif period == 'monthly':
            # Monthly周期：判断月份是否连续
            # 窗口键格式：YYYY-MM_YYYY-MM（例如：2025-01_2025-03）
            try:
                # 解析key1的结束月
                parts1 = key1.split('_')
                year_month1_end = parts1[1]  # YYYY-MM (结束月)
                year1, month1_end = year_month1_end.split('-')
                year1 = int(year1)
                month1_end = int(month1_end)

                # 解析key2的起始月
                parts2 = key2.split('_')
                year_month2_start = parts2[0]  # YYYY-MM (起始月)
                year2, month2_start = year_month2_start.split('-')
                year2 = int(year2)
                month2_start = int(month2_start)

                # 判断连续性
                if year1 == year2:
                    # 同一年：月份连续（month1_end + 1 == month2_start）
                    return (month1_end + 1) == month2_start
                elif year1 + 1 == year2:
                    # 跨年：year1的12月 → year2的1月
                    return month1_end == 12 and month2_start == 1
                else:
                    return False
            except (ValueError, IndexError) as e:
                logger.warning(f"⚠️ 解析月窗口键失败: {key1}, {key2}, error: {e}")
                return False

        else:
            logger.warning(f"⚠️ 不支持的周期: {period}")
            return False

    def _is_first_window(self,
                         window_start: pd.Timestamp,
                         window_end: pd.Timestamp,
                         search_from_date: pd.Timestamp,
                         actual_earliest_date: pd.Timestamp,
                         period: str,
                         market_code: MarketCode) -> bool:
        """
        判断窗口是否为起始窗口（封装所有判断逻辑）

        不同周期的判断逻辑：
        1. 日周期(daily)：
           - 需要精确到交易日判断
           - 确保查询开始时间所在交易日没有数据

        2. 周周期(weekly)：
           - 只需精确到周的比较
           - 确保查询开始时间所在的整个"交易周"没有数据
           - 如果整周都是假期（春节、五一、十一等），需向后推到交易周

        3. 月周期(monthly)：
           - 只需精确到月的比较
           - 确保查询开始时间所在整个月没有数据

        Args:
            window_start:窗口起始时间
            window_end：窗口结束时间
            search_from_date: 查询起始时间
            actual_earliest_date: 本次获取数据的最早开始时间
            period: 数据粒度 (daily/weekly/monthly)
            market_code: 市场代码

        Returns:
            bool: True表示是起始窗口
        """
        search_from_date_no_tz=search_from_date.tz_localize(None)
        actual_earliest_date_no_tz=actual_earliest_date.tz_localize(None)
        if period == 'daily':
            # 日周期：精确到交易日判断
            is_first = self._is_first_window_daily(window_start,
                                                   window_end,
                                                   search_from_date_no_tz,
                                                   actual_earliest_date_no_tz,
                                                   market_code)
        elif period == 'weekly':
            # 周周期：精确到周判断
            is_first = self._is_first_window_weekly(window_start,
                                                    window_end,
                                                    search_from_date_no_tz,
                                                    actual_earliest_date_no_tz,
                                                    market_code)
        elif period == 'monthly':
            # 月周期：精确到月判断
            is_first = self._is_first_window_monthly(window_start,
                                                     window_end,
                                                     search_from_date_no_tz,
                                                     actual_earliest_date_no_tz,
                                                     market_code)
        else:
            # 未知周期，使用保守判断
            is_first = True
            logger.warning(f"未知周期类型: {period}，使用保守判断")
        return is_first

    def _is_first_window_daily(self,
                               window_start: pd.Timestamp,
                               window_end: pd.Timestamp,
                               search_from_date: pd.Timestamp,
                               actual_earliest_date: pd.Timestamp,
                               market_code: MarketCode) -> bool:
        """
        日周期的起始窗口判断
        
        逻辑：
        1. 取 search_from_date 和 window_start 中靠后的那个作为起始日期
        2. 如果起始日期不是交易日，往前推到第一个交易日（更早）
        3. 判断：从起始交易日到最早数据日之间是否有数据
        """
        actual_earliest_date_no_tz=actual_earliest_date.tz_localize(None)
        search_from_date_no_tz=search_from_date.tz_localize(None)
        from_trading_day = search_from_date_no_tz
        if window_start > search_from_date_no_tz:
            from_trading_day = window_start
        
        # 🔧 关键修复：如果不是交易日，往前推到第一个交易日（更早）
        if not self._calendar_service.is_trading_day(market_code, from_trading_day):
            prev_trading_day = self._calendar_service.get_previous_trading_day(market_code, from_trading_day)
            if prev_trading_day:
                from_trading_day = prev_trading_day.tz_localize(None)

        is_first_window = from_trading_day < actual_earliest_date_no_tz <= window_end

        if is_first_window:
            # found_first_window = True
            logger.info(
                f"🅰️ 检测到起始窗口: 日线，查询条件从 {search_from_date.strftime('%Y-%m-%d')}，但数据源最早从 {actual_earliest_date.strftime('%Y-%m-%d')} 开始")
        return is_first_window

    def _is_first_window_weekly(self, window_start: pd.Timestamp,
                                window_end: pd.Timestamp,
                                search_from_date: pd.Timestamp,
                                actual_earliest_date: pd.Timestamp,
                                market_code: MarketCode) -> bool:
        """
        周周期的起始窗口判断

        逻辑：
        1. 取 search_from_date 和 window_start 中靠后的那个作为起始日期
        2. 如果起始日期不是交易日，往前推到第一个交易日（更早）
        3. 获取该交易日所在周的 ISO 周号
        4. 判断：查询开始周 < 最早数据周 <= 当前窗口
        
        判断依据：
        - base_provider 已经过滤了"非交易周"的空数据
        - 保留的空数据周K线都是"有交易但无数据的周"（上市前）
        """
        actual_earliest_date_no_tz=actual_earliest_date.tz_localize(None)
        search_from_date_no_tz=search_from_date.tz_localize(None)
        from_trading_day = search_from_date_no_tz
        if window_start > search_from_date_no_tz:
            from_trading_day = window_start
        
        # 🔧 关键修复：如果不是交易日，往前推到第一个交易日（更早）
        if not self._calendar_service.is_trading_day(market_code, from_trading_day):
            prev_trading_day = self._calendar_service.get_previous_trading_day(market_code, from_trading_day)
            if prev_trading_day:
                from_trading_day = prev_trading_day

        # 🔧 使用 ISO 周号进行比较（与窗口键生成逻辑保持一致）
        # 获取查询开始日期的 ISO 周号
        from_year, from_week, _ = from_trading_day.isocalendar()
        from_year_week = (from_year, from_week)
        
        # 获取最早数据日期的 ISO 周号
        actual_year, actual_week, _ = actual_earliest_date_no_tz.isocalendar()
        actual_year_week = (actual_year, actual_week)
        
        # 获取当前窗口结束日期的 ISO 周号
        to_year, to_week, _ = window_end.isocalendar()
        to_year_week = (to_year, to_week)

        # 判断逻辑：from_year_week < actual_year_week <= to_year_week
        # 这意味着：
        # 1. 查询开始周在最早数据周之前（存在空数据的交易周）
        # 2. 最早数据周在当前窗口范围内
        # 3. 由于 base_provider 已过滤"非交易周"，所以中间的空周都是"有交易但无数据"的周
        is_first_window = from_year_week < actual_year_week <= to_year_week

        if is_first_window:
            logger.info(
                f"🅰️ 检测到起始窗口（周线）: 查询从第 {from_week} 周开始，但数据从第 {actual_week} 周才有，中间存在有交易但无数据的周")
            logger.info(
                f"   查询条件从 {search_from_date_no_tz.strftime('%Y-%m-%d')}，数据源最早从 {actual_earliest_date_no_tz.strftime('%Y-%m-%d')} 开始")
        return is_first_window

    def _is_first_window_monthly(self, window_start: pd.Timestamp,
                                 window_end: pd.Timestamp,
                                 search_from_date: pd.Timestamp,
                                 actual_earliest_date: pd.Timestamp,
                                 market_code: MarketCode) -> bool:
        """
        月周期的起始窗口判断
        
        逻辑：
        1. 取 search_from_date 和 window_start 中靠后的那个作为起始日期
        2. 如果起始日期不是交易日，往前推到第一个交易日（更早）
        3. 判断：查询开始月 < 最早数据月 <= 当前窗口
        """
        actual_earliest_date_no_tz=actual_earliest_date.tz_localize(None)
        search_from_date_no_tz=search_from_date.tz_localize(None)
        from_trading_day = search_from_date_no_tz
        if window_start > search_from_date_no_tz:
            from_trading_day = window_start
        
        # 🔧 关键修复：如果不是交易日，往前推到第一个交易日（更早）
        if not self._calendar_service.is_trading_day(market_code, from_trading_day):
            prev_trading_day = self._calendar_service.get_previous_trading_day(market_code, from_trading_day)
            if prev_trading_day:
                from_trading_day = prev_trading_day
        
        # 只比较年月，不比较具体日期
        from_year_month = (from_trading_day.year, from_trading_day.month)
        actual_earliest_start_month = (actual_earliest_date_no_tz.year, actual_earliest_date_no_tz.month)
        window_end_year_month = (window_end.year, window_end.month)

        is_first_window = from_year_month < actual_earliest_start_month <= window_end_year_month

        if is_first_window:
            logger.info(
                f"🅰️ 检测到起始窗口: 月线，查询条件从 {search_from_date_no_tz.strftime('%Y-%m-%d')}，但数据源最早从 {actual_earliest_date_no_tz.strftime('%Y-%m-%d')} 开始")
        return is_first_window

    def distribute_data_to_windows(self, symbol: str, period: str, data: pd.DataFrame,
                                   reversed_window_keys: list, cached_windows: dict, from_date: pd.Timestamp,
                                   market_code: MarketCode) -> None:
        """
        将大范围数据分配到各个窗口，并写入缓存

        Args:
            symbol: 股票/指数代码
            period: 数据粒度
            data: 大范围查询返回的数据
            reversed_window_keys: 需要分配的窗口键列表
            cached_windows: 已缓存窗口字典 (输出参数)
            from_date: 查询起始日期（用于判断起始窗口）
            market_code: 市场代码枚举，用于交易日历判断
        """
        # 🔧 类型安全检查
        if not isinstance(from_date, pd.Timestamp):
            raise TypeError(f"from_date 必须是 pd.Timestamp 类型，当前类型: {type(from_date).__name__}")
        if not isinstance(market_code, MarketCode):
            raise TypeError(f"market_code 必须是 MarketCode 枚举，当前类型: {type(market_code).__name__}")
        from_date_no_tz = from_date.tz_localize(None)
        if data.empty:
            return

        # 确保数据有 date 列
        if 'date' not in data.columns:
            logger.warning("⚠️ 数据缺少 date 列，无法分配到窗口")
            return

        # 🔧 类型安全：确保 date 列是 datetime 类型，如果转换失败则抛出异常
        try:
            data['date'] = pd.to_datetime(data['date'])
        except Exception as e:
            raise TypeError(f"date 列无法转换为 datetime 类型: {e}")
        
        # 🔧 类型安全：验证转换后的类型
        if not pd.api.types.is_datetime64_any_dtype(data['date']):
            raise TypeError(f"date 列转换后类型不正确: {data['date'].dtype}")

        # 分配数据到各个窗口
        reversed_window_keys = sorted(reversed_window_keys, reverse=True)
        found_first_window = False
        
        # 🔧 关键修复：actual_earliest_date 应该是整个数据集的最早日期，而不是窗口内的最早日期
        global_earliest_date = data['date'].min()
        if len(reversed_window_keys) > 0:
            # range总是以周期为单位，所以range_start可能会早于from_data，例如range_start是周一，
            # 但from_data是周三，那么周一、周二的数据可能为空，不能因此判断周三之前是没有数据，
            # 以此判定符合“上市时间”的条件，因此，判定条件必须以from_data为准
            rang_from_date, _ = self._window_key_to_date_range(reversed_window_keys[len(reversed_window_keys) - 1],
                                                               period)
            if rang_from_date < from_date_no_tz:
                search_from_date = from_date_no_tz
            else:
                search_from_date = rang_from_date
            for idx, window_key in enumerate(reversed_window_keys):
                if found_first_window:
                    break
                window_start, window_end = self._window_key_to_date_range(window_key, period)

                # 筛选该窗口的数据
                window_data = data[(data['date'].values >= window_start.to_datetime64()) & (data['date'].values  <= window_end.to_datetime64())].copy()
                
                if not window_data.empty:
                    is_first_window = self._is_first_window(
                        window_start=window_start,
                        window_end=window_end,
                        search_from_date=search_from_date,
                        actual_earliest_date=global_earliest_date,
                        period=period,
                        market_code=market_code
                    )

                    self._fast_cache.set(symbol, period, window_key, window_data, is_first_window=is_first_window)
                    cached_windows[window_key] = window_data
                    if is_first_window:
                        found_first_window = True
                else:
                    # 已知空窗口：只记标记，不存空 DF
                    self._fast_cache.set(symbol, period, window_key, known_empty=True)

    def _backfill_first_window_flag(self, symbol: str, period: str, actual_earliest_start: pd.Timestamp,
                                    current_window_keys: list, market_code: MarketCode = MarketCode.CN) -> None:
        """
        回溯更新起始窗口标记

        场景：
        - 首次查询正好从上市日开始（如 2025-01-08 ~ 2025-01-12）
        - query_start == actual_earliest_start，未被标记为起始窗口
        - 第二次查询包含更早日期（如 2025-01-06 ~ 2025-01-12）
        - 检测到 query_start < actual_earliest_start，确认为起始窗口
        - 需要回溯更新之前缓存中包含 actual_earliest_start 的窗口

        Args:
            symbol: 股票/指数代码
            period: 数据粒度/K线类型
            actual_earliest_start: 数据源返回的实际最早日期（上市日）
            current_window_keys: 当前查询涉及的窗口键列表（避免重复更新）
        """
        # 生成包含 actual_earliest_start 的窗口键
        actual_earliest_start_no_tz=actual_earliest_start.tz_localize(None)
        first_data_window_key = self._make_window_key(actual_earliest_start_no_tz, period)

        # 如果当前查询已经处理过这个窗口，无需回溯
        if first_data_window_key in current_window_keys:
            return

        # 尝试更新该窗口的标记
        if hasattr(self._fast_cache, 'update_first_window_flag'):
            updated = self._fast_cache.update_first_window_flag(
                symbol, period, first_data_window_key, is_first_window=True
            )

            if updated:
                logger.info(f"✅ 回溯成功: 更新窗口 {first_data_window_key} 为起始窗口")

    def get_cached_and_missing_windows(self,
                                       symbol: str,
                                       start_date: pd.Timestamp,
                                       end_date: pd.Timestamp,
                                       market_code: MarketCode = MarketCode.CN,
                                       period: str = "daily",
                                       current_time: pd.Timestamp = None):
        # ========== 第1步：生成所需的所有窗口键 ==========
        start_date_no_tz=start_date.tz_localize(None)
        end_date_no_tz=end_date.tz_localize(None)
        window_keys = self._generate_window_keys(start_date_no_tz, end_date_no_tz, period, market_code)
        # ========== 第2步：从快速缓存获取已有窗口 ==========
        cached_windows = {}
        missing_windows = []
        first_window_key = None  # 记录起始窗口（最早数据）
        for window_key in window_keys:
            cached_value = self._fast_cache.get(symbol, period, window_key)
            if cached_value is not None:
                # 缓存返回dict：{'data': df, 'is_first_window': bool, 'timestamp': float, 'known_empty': bool}
                cached_df = cached_value.get('data')
                is_first = cached_value.get('is_first_window', False)
                is_known_empty = cached_value.get('known_empty', False)

                # 记录起始窗口
                if is_first:
                    first_window_key = window_key
                    logger.info(f"🅰️ 检测到起始窗口: {window_key} (最早数据)")

                # 检查是否早于已知的起始窗口
                if first_window_key is not None and window_key < first_window_key:
                    logger.info(f"🚫 已忽略早于起始窗口 {first_window_key} 的缓存窗口 {window_key}")
                else:
                    if is_known_empty:
                        logger.debug(f"🏷️ 已知空窗口命中: {window_key} (跳过重查，不参与合并)")
                    else:
                        cached_windows[window_key] = cached_df
            else:
                # 缺失窗口
                missing_windows.append(window_key)
        # 检查是否有比起始窗口更早的查询
        if first_window_key is not None:
            # 移除所有早于起始窗口的请求
            original_count = len(missing_windows)
            missing_windows = [w for w in missing_windows if w >= first_window_key]
            removed_count = original_count - len(missing_windows)

            if removed_count > 0:
                logger.info(f"🚫 已忽略 {removed_count} 个早于起始窗口 {first_window_key} 的查询")
        logger.info(f"✅ {'memory'}命中: {len(cached_windows)}/{len(window_keys)} 个窗口")
        return cached_windows, missing_windows

    def clear_all_cache(self) -> None:
        """清空所有层级的缓存"""
        self._fast_cache.clear()
        logger.info(f"✅ 所有缓存已清空 (cache_mode={'memory'})")

    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        return {
            'cache_mode': 'memory',
            'memory': self._fast_cache.get_stats()
        }
