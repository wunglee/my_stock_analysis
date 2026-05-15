"""MockDataProvider 单元测试

测试对象：core/data/providers/mock_provider.py
覆盖范围：
- get_prices() 方法：历史K线数据生成
- get_realtime_kline() 方法：实时K线数据
- set_mock_trading_phase() 方法：Mock交易时段设置
- set_needs_realtime_kline() 方法：实时K线需求判断
- _fetch_from_external_api() 方法：历史数据范围控制
"""

import unittest

import pandas as pd
from core.data.providers.mock_provider import MockDataProvider
from core.data.providers.protocols import PriceData
from core.share.market.market_enums import TradingPhase


class MockProviderTest(unittest.TestCase):
    """MockDataProvider完整测试套件"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = MockDataProvider()
    
    # ========== _fetch_from_external_api() 方法测试（历史K线生成）==========
    
    def test_fetch_basic_generation(self):
        """测试基本K线数据生成"""
        symbol = '000300.SH'
        start_date = '2024-01-02'
        end_date = '2024-01-05'
        
        result = self.provider._fetch_history_kline_from_external_api(symbol, start_date, end_date)
        df = result.to_dataframe()
        
        # 验证数据条数和列名
        self.assertEqual(len(df), 4)
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            self.assertIn(col, df.columns)
        
        # 验证日期范围
        self.assertEqual(df['date'].iloc[0], pd.Timestamp('2024-01-02'))
        self.assertEqual(df['date'].iloc[-1], pd.Timestamp('2024-01-05'))
    
    def test_fetch_skip_weekends(self):
        """测试跳过周末逻辑"""
        symbol = '000300.SH'
        start_date = '2024-01-05'  # 周五
        end_date = '2024-01-10'    # 周三
        
        result = self.provider._fetch_history_kline_from_external_api(symbol, start_date, end_date)
        df = result.to_dataframe()
        
        # 验证跳过周末
        self.assertEqual(len(df), 4)
        dates = df['date'].tolist()
        self.assertIn(pd.Timestamp('2024-01-05'), dates)
        self.assertNotIn(pd.Timestamp('2024-01-06'), dates)
        self.assertNotIn(pd.Timestamp('2024-01-07'), dates)
        self.assertIn(pd.Timestamp('2024-01-08'), dates)
    
    def test_fetch_ohlc_validity(self):
        """测试OHLC数据合法性"""
        symbol = '000300.SH'
        start_date = '2024-01-02'
        end_date = '2024-01-10'
        
        result = self.provider._fetch_history_kline_from_external_api(symbol, start_date, end_date)
        df = result.to_dataframe()
        
        for _, row in df.iterrows():
            # 验证价格关系
            self.assertGreaterEqual(row['high'], row['open'])
            self.assertGreaterEqual(row['high'], row['close'])
            self.assertLessEqual(row['low'], row['open'])
            self.assertLessEqual(row['low'], row['close'])
            self.assertGreaterEqual(row['high'], row['low'])
            
            # 验证成交量和价格为正
            self.assertGreater(row['volume'], 0)
            self.assertGreater(row['open'], 0)
    
    def test_fetch_repeatability(self):
        """测试数据可重复性"""
        symbol = '000300.SH'
        start_date = '2024-01-02'
        end_date = '2024-01-05'
        
        result1 = self.provider._fetch_history_kline_from_external_api(symbol, start_date, end_date)
        result2 = self.provider._fetch_history_kline_from_external_api(symbol, start_date, end_date)
        
        df1 = result1.to_dataframe()
        df2 = result2.to_dataframe()
        
        # 验证数据完全相同
        self.assertEqual(len(df1), len(df2))
        for idx in range(len(df1)):
            self.assertEqual(df1['open'].iloc[idx], df2['open'].iloc[idx])
            self.assertEqual(df1['close'].iloc[idx], df2['close'].iloc[idx])
    
    # ========== get_realtime_kline() 方法测试 ==========
    
    def test_get_realtime_kline_trading_phase(self):
        """测试盘中时段K线计算"""
        symbol = '000001.SZ'
        trade_date = '2025-12-16'
        
        result = self.provider.get_realtime_kline(
            symbol, trade_date, TradingPhase.TRADING, is_index=False
        )
        
        # 验证结果
        self.assertEqual(result['date'], '2025-12-16')
        self.assertIsNotNone(result['open'])
        self.assertGreaterEqual(result['high'], result['open'])
        self.assertLessEqual(result['low'], result['open'])
        self.assertEqual(result['trading_phase'], 'trading')
        self.assertTrue(result['should_poll'])
    
    def test_get_realtime_kline_before_open(self):
        """测试盘前时段（集合竞价）"""
        symbol = '000001.SZ'
        trade_date = '2025-12-16'
        
        result = self.provider.get_realtime_kline(
            symbol, trade_date, TradingPhase.BEFORE_OPEN, is_index=False
        )
        
        # 盘前OHLC相同
        self.assertEqual(result['open'], result['high'])
        self.assertEqual(result['open'], result['low'])
        self.assertEqual(result['open'], result['close'])
        self.assertEqual(result['volume'], 0)
        self.assertEqual(result['trading_phase'], 'before_open')
        self.assertTrue(result['should_poll'])
    
    def test_get_realtime_kline_after_close(self):
        """测试盘后时段"""
        symbol = '000001.SZ'
        trade_date = '2025-12-16'
        
        result = self.provider.get_realtime_kline(
            symbol, trade_date, TradingPhase.AFTER_CLOSE, is_index=False
        )
        
        self.assertIsNotNone(result['open'])
        self.assertGreaterEqual(result['high'], result['low'])
        self.assertEqual(result['trading_phase'], 'after_close')
        self.assertFalse(result['should_poll'])
    
    def test_get_realtime_kline_cache(self):
        """测试缓存机制"""
        symbol = '000001.SZ'
        trade_date = '2025-12-16'
        
        # 第一次调用
        first_result = self.provider.get_realtime_kline(
            symbol, trade_date, TradingPhase.TRADING, is_index=False
        )
        first_open = first_result['open']
        
        # 第二次调用（使用缓存）
        second_result = self.provider.get_realtime_kline(
            symbol, trade_date, TradingPhase.TRADING, is_index=False, cached=first_result
        )
        
        # 验证开盘价复用缓存
        self.assertEqual(second_result['open'], first_open)
    
    # ========== set_mock_trading_phase() 和 set_needs_realtime_kline() 测试 ==========
    
    def test_set_mock_trading_phase_before_open(self):
        """测试设置盘前时段后，needs_realtime_kline应为True"""
        self.provider.set_mock_trading_phase(TradingPhase.BEFORE_OPEN)
        
        df = pd.DataFrame([
            {'date': '2025-12-16', 'open': 100, 'high': 105, 'low': 99, 'close': 103, 'volume': 1000000}
        ])
        price_data = PriceData.from_dataframe(df, '000001.SZ')
        
        self.provider.set_needs_realtime_kline(price_data, pd.Timestamp.now())
        
        self.assertTrue(price_data.needs_realtime_kline)
    
    def test_set_mock_trading_phase_trading(self):
        """测试设置盘中时段后，needs_realtime_kline应为True"""
        self.provider.set_mock_trading_phase(TradingPhase.TRADING)
        
        df = pd.DataFrame([
            {'date': '2025-12-16', 'open': 100, 'high': 105, 'low': 99, 'close': 103, 'volume': 1000000}
        ])
        price_data = PriceData.from_dataframe(df, '000001.SZ')
        
        self.provider.set_needs_realtime_kline(price_data, pd.Timestamp.now())
        
        self.assertTrue(price_data.needs_realtime_kline)
    
    def test_set_mock_trading_phase_after_close(self):
        """测试设置盘后时段后，needs_realtime_kline应为False"""
        self.provider.set_mock_trading_phase(TradingPhase.AFTER_CLOSE)
        
        df = pd.DataFrame([
            {'date': '2025-12-16', 'open': 100, 'high': 105, 'low': 99, 'close': 103, 'volume': 1000000}
        ])
        price_data = PriceData.from_dataframe(df, '000001.SZ')
        
        self.provider.set_needs_realtime_kline(price_data, pd.Timestamp.now())
        
        self.assertFalse(price_data.needs_realtime_kline)
    
    # ========== _fetch_from_external_api() 历史数据范围控制测试 ==========
    
    def test_historical_kline_excludes_today_before_open(self):
        """测试盘前时段历史K线不包含今天"""
        self.provider.set_mock_trading_phase(TradingPhase.BEFORE_OPEN)
        
        today = pd.Timestamp.today().normalize()
        if today.weekday() >= 5:
            self.skipTest("周末跳过测试")
        
        today_str = today.strftime('%Y-%m-%d')
        start_date = (today - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
        
        price_data = self.provider._fetch_history_kline_from_external_api(
            '000300.SH', start_date, today_str, 'daily'
        )
        
        last_date = price_data.records[-1].date
        last_date_str = last_date.strftime('%Y-%m-%d') if isinstance(last_date, pd.Timestamp) else str(last_date)
        self.assertNotEqual(last_date_str, today_str, "盘前时段历史K线不应包含今天")
    
    def test_historical_kline_excludes_today_trading(self):
        """测试盘中时段历史K线不包含今天"""
        self.provider.set_mock_trading_phase(TradingPhase.TRADING)
        
        today = pd.Timestamp.today().normalize()
        if today.weekday() >= 5:
            self.skipTest("周末跳过测试")
        
        today_str = today.strftime('%Y-%m-%d')
        start_date = (today - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
        
        price_data = self.provider._fetch_history_kline_from_external_api(
            '000300.SH', start_date, today_str, 'daily'
        )
        
        last_date = price_data.records[-1].date
        last_date_str = last_date.strftime('%Y-%m-%d') if isinstance(last_date, pd.Timestamp) else str(last_date)
        self.assertNotEqual(last_date_str, today_str, "盘中时段历史K线不应包含今天")
    
    def test_historical_kline_includes_today_after_close(self):
        """测试盘后时段历史K线包含今天"""
        self.provider.set_mock_trading_phase(TradingPhase.AFTER_CLOSE)
        
        today = pd.Timestamp.today().normalize()
        if today.weekday() >= 5:
            self.skipTest("周末跳过测试")
        
        today_str = today.strftime('%Y-%m-%d')
        start_date = (today - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
        
        price_data = self.provider._fetch_history_kline_from_external_api(
            '000300.SH', start_date, today_str, 'daily'
        )
        
        last_date = price_data.records[-1].date
        last_date_str = last_date.strftime('%Y-%m-%d') if isinstance(last_date, pd.Timestamp) else str(last_date)
        self.assertEqual(last_date_str, today_str, "盘后时段历史K线应包含今天")


if __name__ == '__main__':
    unittest.main()
