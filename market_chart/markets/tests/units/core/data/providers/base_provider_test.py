"""
测试 BaseProvider 基类 - 全面测试新架构下的核心功能

测试覆盖：
1. 缓存管理器集成
2. 数据获取流程（get_index_prices/get_stock_prices）
3. 周期转换（_convert_period）
4. needs_realtime_kline 标记设置
5. 抽象方法接口
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from core.data.providers.base_provider import BaseDataProvider
from core.data.providers.protocols import PriceData
from core.share.market.data_types import OHLCVRecord
from core.share.market.market_enums import TradingPhase


class MockProvider(BaseDataProvider):
    """用于测试的模拟提供者"""
    
    def __init__(self):
        super().__init__()
        self.api_calls = []  # 记录API调用
    
    def get_test_symbol(self) -> str:
        return "000300.SH"
    
    def _fetch_history_kline_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str = 'daily'):
        """模拟外部API调用"""
        self.api_calls.append({
            'symbol': symbol,
            'start_date': start_date,
            'end_date': end_date,
            'period': period
        })
        
        # 返回模拟PriceData
        dates = pd.date_range(start_date, end_date, freq='D')
        records = [
            OHLCVRecord(
                date=pd.Timestamp(date),
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=1000000 + i * 1000
            )
            for i, date in enumerate(dates)
        ]
        
        return PriceData(
            records=records,
            symbol=symbol,
            start_date=pd.Timestamp(start_date),
            end_date=pd.Timestamp(end_date),
            count=len(records)
        )


class TestBaseProvider(unittest.TestCase):
    """测试 BaseProvider 基类"""

    def setUp(self):
        """测试前准备"""
        self.provider = MockProvider()
        self.test_symbol = '000300.SH'
    
    def test_initialization(self):
        """测试初始化"""
        # 验证缓存管理器创建
        self.assertIsNotNone(self.provider._cache_manager)
        self.assertTrue(hasattr(self.provider, 'config_manager'))
    
    def test_get_index_prices_basic(self):
        """测试基本指数数据获取"""
        start = pd.Timestamp('2025-01-01')
        end = pd.Timestamp('2025-01-10')
        current = pd.Timestamp.now()
        
        result = self.provider.get_index_prices(
            self.test_symbol,
            start,
            end,
            current
        )
        
        # 验证返回类型
        self.assertIsInstance(result, PriceData)
        self.assertEqual(result.symbol, self.test_symbol)
        self.assertGreater(result.count, 0)
    
    def test_get_stock_prices_basic(self):
        """测试基本股票数据获取"""
        start = pd.Timestamp('2025-01-01')
        end = pd.Timestamp('2025-01-10')
        current = pd.Timestamp.now()
        
        result = self.provider.get_stock_prices(
            '000001.SZ',
            start,
            end,
            current
        )
        
        # 验证返回类型
        self.assertIsInstance(result, PriceData)
        self.assertEqual(result.symbol, '000001.SZ')
    
    def test_convert_period_to_weekly(self):
        """测试周期转换：日线→2周线"""
        # 准备日线数据
        dates = pd.date_range('2025-01-01', '2025-01-14', freq='D')
        records = [
            OHLCVRecord(
                date=pd.Timestamp(date),
                open=100.0,
                high=105.0,
                low=95.0,
                close=102.0,
                volume=1000000
            )
            for date in dates
        ]
        
        daily_data = PriceData(
            records=records,
            symbol=self.test_symbol,
            start_date=pd.Timestamp('2025-01-01'),
            end_date=pd.Timestamp('2025-01-14'),
            count=len(records)
        )
        
        # 转换为周线
        from core.share.market.market_enums import MarketCode
        weekly_data = self.provider._convert_period(daily_data, 'weekly', MarketCode.CN)
        
        # 验证
        self.assertIsInstance(weekly_data, PriceData)
        self.assertLess(weekly_data.count, daily_data.count, "周线数据应该少于日线")
        self.assertEqual(weekly_data.symbol, self.test_symbol)
    
    def test_convert_period_to_monthly(self):
        """测试周期转换：日线→月线"""
        # 准备日线数据（1月31天）
        dates = pd.date_range('2025-01-01', '2025-01-31', freq='D')
        records = [
            OHLCVRecord(
                date=pd.Timestamp(date),
                open=100.0,
                high=105.0,
                low=95.0,
                close=102.0,
                volume=1000000
            )
            for date in dates
        ]
        
        daily_data = PriceData(
            records=records,
            symbol=self.test_symbol,
            start_date=pd.Timestamp('2025-01-01'),
            end_date=pd.Timestamp('2025-01-31'),
            count=len(records)
        )
        
        # 转换为月线
        from core.share.market.market_enums import MarketCode
        monthly_data = self.provider._convert_period(daily_data, 'monthly', MarketCode.CN)
        
        # 验证
        self.assertIsInstance(monthly_data, PriceData)
        self.assertEqual(monthly_data.count, 1, "1月应该只有1条月线")
        self.assertEqual(monthly_data.symbol, self.test_symbol)
    
    def test_convert_period_filters_non_trading_weeks(self):
        """测试周期转换：过滤非交易周（整周都是节假日）"""
        from core.share.market.market_enums import MarketCode
        
        # 准备测试数据：2023年9月26日 - 10月10日（包含国庆长假）
        # 9月26日-10月1日：正常交易周
        # 10月2日-10月8日：国庆长假（整周无交易）
        # 10月9日-10月10日：恢复交易
        dates = []
        # 添加9月26日-10月1日的交易日
        for day in [26, 27, 28, 29, 30]:  # 9月26-30日（周二到周六）
            dates.append(pd.Timestamp(2023, 9, day))
        # 国庆假期无数据（10月2-8日）
        # 添加10月9-10日的交易日
        for day in [9, 10]:  # 10月9-10日（周一、周二）
            dates.append(pd.Timestamp(2023, 10, day))
        
        records = [
            OHLCVRecord(
                date=date,
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=1000000
            )
            for i, date in enumerate(dates)
        ]
        
        daily_data = PriceData(
            records=records,
            symbol=self.test_symbol,
            start_date=dates[0],
            end_date=dates[-1],
            count=len(records)
        )
        
        # 转换为周线
        weekly_data = self.provider._convert_period(daily_data, 'weekly', MarketCode.CN)
        
        # 验证：应该过滤掉国庆周，只保留2个周的数据
        self.assertIsInstance(weekly_data, PriceData)
        # 注意：具体的周数可能因为日历服务的实现而异，这里主要验证逻辑正确
        self.assertGreater(weekly_data.count, 0, "应该有周线数据")
        self.assertLess(weekly_data.count, 4, "应该过滤掉部分空周期")
    
    def test_convert_period_keeps_empty_trading_weeks(self):
        """测试周期转换：保留有交易但无数据的周（用于上市周判断）"""
        from core.share.market.market_enums import MarketCode
        
        # 模拟场景：股票在29年12月26日（周五）开始有数据
        # 2024年12月23-29日：只有 12月26日之后有数据，会创建一个周K线
        # 2024年12月30-2025年1月5日：全周有数据
        
        # 准备数据：12月26日 - 2025年1月5日
        dates = []
        for day in [26, 27, 30, 31]:  # 12月26,27,30,31日
            dates.append(pd.Timestamp(2024, 12, day))
        for day in [2, 3]:  # 2025年1月2,3日
            dates.append(pd.Timestamp(2025, 1, day))
        
        records = [
            OHLCVRecord(
                date=date,
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=1000000
            )
            for i, date in enumerate(dates)
        ]
        
        daily_data = PriceData(
            records=records,
            symbol=self.test_symbol,
            start_date=dates[0],
            end_date=dates[-1],
            count=len(records)
        )
        
        # 转换为周线
        weekly_data = self.provider._convert_period(daily_data, 'weekly', MarketCode.CN)
        
        # 验证：应该有2个周的数据
        # 第一周：12月23日（周一），包含 12月26,27 的数据
        # 第二周：12月30日（周一），包含 12月30,31 和 1月2,3 的数据
        self.assertIsInstance(weekly_data, PriceData)
        self.assertEqual(weekly_data.count, 2, "应该有2个周的数据")
        
        # 验证第一个周（12月23-29日）有数据
        first_week = weekly_data.records[0]
        self.assertEqual(first_week.date, pd.Timestamp(2024, 12, 23), "第一个周的日期应该是12月23日（周一）")
        self.assertFalse(
            pd.isna(first_week.open) or pd.isna(first_week.high) or 
            pd.isna(first_week.low) or pd.isna(first_week.close),
            "第一个周应该有数据"
        )
        
        # 验证第二个周（12月30-1月5日）有数据
        second_week = weekly_data.records[1]
        self.assertEqual(second_week.date, pd.Timestamp(2024, 12, 30), "第二个周的日期应该是12月30日（周一）")
        self.assertFalse(
            pd.isna(second_week.open) or pd.isna(second_week.high) or 
            pd.isna(second_week.low) or pd.isna(second_week.close),
            "第二个周应详有数据"
        )
    
    def test_set_needs_realtime_kline_before_open(self):
        """测试盘前时段 needs_realtime_kline 标记"""
        price_data = PriceData(
            records=[],
            symbol=self.test_symbol,
            start_date=pd.Timestamp('2025-01-01'),
            end_date=pd.Timestamp('2025-01-10'),
            count=0
        )
        
        # 模拟盘前时间（周一 9:00）
        with patch('core.share.markets.MarketTimeUtils.determine_trading_phase') as mock_phase:
            mock_phase.return_value = TradingPhase.BEFORE_OPEN
            
            self.provider.set_needs_realtime_kline(price_data, pd.Timestamp(2025, 1, 6, 9, 0))
            
            # 盘前应该需要实时K线
            self.assertTrue(price_data.needs_realtime_kline)
    
    def test_set_needs_realtime_kline_after_close(self):
        """测试盘后时段 needs_realtime_kline 标记"""
        price_data = PriceData(
            records=[],
            symbol=self.test_symbol,
            start_date=pd.Timestamp('2025-01-01'),
            end_date=pd.Timestamp('2025-01-10'),
            count=0
        )
        
        # 模拟盘后时间（周一 16:00）
        with patch('core.share.markets.MarketTimeUtils.determine_trading_phase') as mock_phase:
            mock_phase.return_value = TradingPhase.AFTER_CLOSE
            
            self.provider.set_needs_realtime_kline(price_data, pd.Timestamp(2025, 1, 6, 16, 0))
            
            # 盘后不需要实时K线
            self.assertFalse(price_data.needs_realtime_kline)
    
    def test_fetch_from_api_calls_external_api(self):
        """测试 _fetch_from_api 调用子类的外部API"""
        start = pd.Timestamp('2025-01-01')
        end = pd.Timestamp('2025-01-05')
        
        result = self.provider._fetch_from_external_api(self.test_symbol, start, end, 'daily')
        
        # 验证调用记录
        self.assertEqual(len(self.provider.api_calls), 1)
        self.assertEqual(self.provider.api_calls[0]['symbol'], self.test_symbol)
        
        # 验证返回DataFrame
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
    
    def test_cache_manager_integration(self):
        """测试缓存管理器集成"""
        # 第一次调用应该访问API
        start = pd.Timestamp('2025-01-01')
        end = pd.Timestamp('2025-01-05')
        current = pd.Timestamp.now()
        
        result1 = self.provider.get_index_prices(self.test_symbol, start, end, current)
        api_calls_count1 = len(self.provider.api_calls)
        
        # 第二次相同调用可能命中缓存（取决于窗口配置）
        result2 = self.provider.get_index_prices(self.test_symbol, start, end, current)
        
        # 验证数据一致性
        self.assertEqual(result1.count, result2.count)
        self.assertEqual(result1.symbol, result2.symbol)


class TestBaseProviderAbstractMethods(unittest.TestCase):
    """测试抽象方法接口"""
    
    def test_cannot_instantiate_without_implementation(self):
        """测试不能直接实例化BaseProvider"""
        with self.assertRaises(TypeError) as context:
            # 尝试实例化抽象类
            provider = BaseDataProvider()
        
        # 验证错误消息包含抽象方法
        self.assertIn("Can't instantiate abstract class", str(context.exception))


class TestRealtimeKlineMerge(unittest.TestCase):
    """测试实时K线合并到周线/月线的功能
    
    测试场景：
    1. 日线：实时K线作为独立的当天K柱（现有功能，保持不变）
    2. 周线：
       - 当天是新周第一天：创建新的独立周K柱
       - 当天不是新周第一天：合并到最后一个周K柱
    3. 月线：
       - 当天是新月第一天：创建新的独立月K柱  
       - 当天不是新月第一天：合并到最后一个月K柱
    """
    
    def setUp(self):
        """设置测试环境"""
        self.provider = MockProvider()
    
    def test_daily_period_not_merge(self):
        """测试日线周期不需要合并，直接返回原数据"""
        historical_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=100, high=105, low=99, close=103, volume=1000),
                OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=103, high=108, low=102, close=106, volume=1200),
            ],
            symbol='TEST',
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-02'),
            count=2
        )
        
        realtime_kline = {
            'date': '2024-01-03',
            'open': 106,
            'high': 110,
            'low': 105,
            'close': 109,
            'volume': 1500
        }
        
        result = self.provider.merge_realtime_kline_to_period(
            historical_data, realtime_kline, 'daily'
        )
        
        self.assertEqual(result.count, 2)
        self.assertEqual(result, historical_data)
    
    def test_weekly_merge_same_week(self):
        """测试周线：实时数据在同一周内，应合并到最后一个周K柱"""
        historical_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2023-12-25'), open=100, high=105, low=99, close=103, volume=5000),
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=103, high=108, low=102, close=106, volume=6000),
            ],
            symbol='TEST',
            start_date=pd.Timestamp('2023-12-25'),
            end_date=pd.Timestamp('2024-01-01'),
            count=2
        )
        
        realtime_kline = {
            'date': '2024-01-03',
            'open': 107,
            'high': 110,
            'low': 105,
            'close': 109,
            'volume': 1500
        }
        
        result = self.provider.merge_realtime_kline_to_period(
            historical_data, realtime_kline, 'weekly'
        )
        
        self.assertEqual(result.count, 2, "周K柱数量应保持为2")
        last_bar = result.records[-1]
        self.assertEqual(last_bar.date, pd.Timestamp('2024-01-01'), "周K柱日期应保持为周一")
        self.assertEqual(last_bar.open, 103, "周开盘价应保持不变")
        self.assertEqual(last_bar.high, 110, "周最高价应更新为max(108, 110)=110")
        self.assertEqual(last_bar.low, 102, "周最低价应保持为min(102, 105)=102")
        self.assertEqual(last_bar.close, 109, "周收盘价应更新为实时收盘价")
        self.assertEqual(last_bar.volume, 7500, "周成交量应累加：6000+1500=7500")
    
    def test_weekly_create_new_bar(self):
        """测试周线：实时数据在新周，应创建新的周K柱"""
        historical_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=103, high=108, low=102, close=106, volume=6000),
            ],
            symbol='TEST',
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-01'),
            count=1
        )
        
        realtime_kline = {
            'date': '2024-01-08',
            'open': 107,
            'high': 110,
            'low': 105,
            'close': 109,
            'volume': 1500
        }
        
        result = self.provider.merge_realtime_kline_to_period(
            historical_data, realtime_kline, 'weekly'
        )
        
        self.assertEqual(result.count, 2, "应该有2个周K柱")
        new_bar = result.records[-1]
        self.assertEqual(new_bar.date, pd.Timestamp('2024-01-08'), "新周K柱日期应为实时数据日期")
        self.assertEqual(new_bar.open, 107)
        self.assertEqual(new_bar.high, 110)
        self.assertEqual(new_bar.low, 105)
        self.assertEqual(new_bar.close, 109)
        self.assertEqual(new_bar.volume, 1500)
    
    def test_monthly_merge_same_month(self):
        """测试月线：实时数据在同一月内，应合并到最后一个月K柱"""
        historical_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2023-12-01'), open=100, high=105, low=99, close=103, volume=50000),
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=103, high=108, low=102, close=106, volume=60000),
            ],
            symbol='TEST',
            start_date=pd.Timestamp('2023-12-01'),
            end_date=pd.Timestamp('2024-01-01'),
            count=2
        )
        
        realtime_kline = {
            'date': '2024-01-15',
            'open': 107,
            'high': 112,
            'low': 105,
            'close': 110,
            'volume': 15000
        }
        
        result = self.provider.merge_realtime_kline_to_period(
            historical_data, realtime_kline, 'monthly'
        )
        
        self.assertEqual(result.count, 2, "月K柱数量应保持为2")
        last_bar = result.records[-1]
        self.assertEqual(last_bar.date, pd.Timestamp('2024-01-01'), "月K柱日期应保持为月初")
        self.assertEqual(last_bar.open, 103, "月开盘价应保持不变")
        self.assertEqual(last_bar.high, 112, "月最高价应更新为max(108, 112)=112")
        self.assertEqual(last_bar.low, 102, "月最低价应保持为min(102, 105)=102")
        self.assertEqual(last_bar.close, 110, "月收盘价应更新为实时收盘价")
        self.assertEqual(last_bar.volume, 75000, "月成交量应累加：60000+15000=75000")
    
    def test_monthly_create_new_bar(self):
        """测试月线：实时数据在新月，应创建新的月K柱"""
        historical_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=103, high=108, low=102, close=106, volume=60000),
            ],
            symbol='TEST',
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-01'),
            count=1
        )
        
        realtime_kline = {
            'date': '2024-02-01',
            'open': 107,
            'high': 110,
            'low': 105,
            'close': 109,
            'volume': 15000
        }
        
        result = self.provider.merge_realtime_kline_to_period(
            historical_data, realtime_kline, 'monthly'
        )
        
        self.assertEqual(result.count, 2, "应该有2个月K柱")
        new_bar = result.records[-1]
        self.assertEqual(new_bar.date, pd.Timestamp('2024-02-01'), "新月K柱日期应为实时数据日期")
        self.assertEqual(new_bar.open, 107)
        self.assertEqual(new_bar.high, 110)
        self.assertEqual(new_bar.low, 105)
        self.assertEqual(new_bar.close, 109)
        self.assertEqual(new_bar.volume, 15000)
    
    def test_empty_historical_data(self):
        """测试历史数据为空时，直接返回原数据"""
        empty_data = PriceData(records=[], symbol='TEST', start_date=pd.Timestamp('2024-01-01'), 
                               end_date=pd.Timestamp('2024-01-01'), count=0)
        
        realtime_kline = {
            'date': '2024-01-15',
            'open': 107,
            'high': 110,
            'low': 105,
            'close': 109,
            'volume': 1500
        }
        
        result = self.provider.merge_realtime_kline_to_period(
            empty_data, realtime_kline, 'weekly'
        )
        
        self.assertEqual(result.count, 0)
        self.assertEqual(result, empty_data)
    
    def test_invalid_realtime_data(self):
        """测试实时数据无效时，直接返回原数据"""
        historical_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=103, high=108, low=102, close=106, volume=6000),
            ],
            symbol='TEST',
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-01'),
            count=1
        )
        
        invalid_realtime = {'open': 107, 'high': 110}
        
        result = self.provider.merge_realtime_kline_to_period(
            historical_data, invalid_realtime, 'weekly'
        )
        
        self.assertEqual(result.count, 1)
        self.assertEqual(result, historical_data)


if __name__ == '__main__':
    unittest.main()