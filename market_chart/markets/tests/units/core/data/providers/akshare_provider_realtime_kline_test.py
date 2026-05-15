"""
AKShareDataProvider.get_realtime_kline 方法单元测试

状态：新增功能测试
覆盖范围：
- 交易时段K线计算（缓存命中/未命中）
- 盘前时段集合竞价价格
- 盘后时段处理
- 异常情况处理
"""

import unittest

from unittest.mock import Mock, patch

import pandas as pd

from core.data.providers.akshare_provider import AKShareDataProvider
from core.data.providers.protocols import (
    IntradayTickRecord,
    IntradayData,
    OrderBookLevel
)
from core.share.market.market_enums import MarketCode


class AKShareProviderRealtimeKlineTest(unittest.TestCase):
    """AKShareDataProvider实时K线测试"""

    def setUp(self):
        """测试前准备"""
        # 直接创建provider实例（akshare不需要credentials）
        with patch.object(AKShareDataProvider, '_initialize'):
            with patch.object(AKShareDataProvider, '_load_us_symbol_mapping'):
                self.provider = AKShareDataProvider()
                # Mock akshare接口
                self.provider.ak = Mock()
                self.provider.available = True
                self.provider.logger = Mock()

    def test_trading_phase_no_cache(self):
        """测试盘中时段K线计算（无缓存）"""
        # 准备测试数据
        symbol = '000001.SZ'
        test_time = pd.Timestamp(2025, 12, 16, 10, 30, 0)  # 盘中时间

        # Mock分时数据
        mock_ticks = [
            IntradayTickRecord(time='09:30', price=10.0, volume=1000, avg_price=10.0),
            IntradayTickRecord(time='10:00', price=10.5, volume=1500, avg_price=10.25),
            IntradayTickRecord(time='10:30', price=10.3, volume=1200, avg_price=10.27)
        ]
        mock_intraday = IntradayData(
            symbol=symbol,
            name='平安银行',
            current_price=10.3,
            yesterday_close=10.2,
            change=0.1,
            change_percent=0.98,
            ticks=mock_ticks,
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2025-12-16'),
            order_book_message='',
            trade_records_message='',
            is_index=False,
            should_poll=True
        )

        # Mock akshare分钟数据（用于更新K线）
        mock_minute_df = pd.DataFrame({
            '时间': ['2025-12-16 10:30:00'],
            '开盘': [10.0],
            '收盘': [10.3],
            '最高': [10.6],
            '最低': [9.9],
            '成交量': [500],
            '成交额': [5000],
            '振幅': [0.7],
            '涨跌幅': [0.98],
            '涨跌额': [0.1],
            '换手率': [0.5]
        })

        with patch.object(self.provider, 'get_intraday_data', return_value=mock_intraday):
            with patch.object(self.provider, '_get_from_memory_cache', return_value=None):
                with patch.object(self.provider, '_set_to_memory_cache_obj') as mock_set_cache:
                    with patch.object(self.provider, '_map_to_akshare', return_value='000001'):
                        with patch.object(self.provider.ak, 'stock_zh_a_hist_min_em', return_value=mock_minute_df):
                            # 执行方法
                            result = self.provider._get_today_k_column(symbol, test_time)

        # 验证结果
        self.assertEqual(result['date'], '2025-12-16')
        self.assertIsNotNone(result['open'])  # 应该有开盘价
        self.assertIsNotNone(result['close'])  # 应该有收盘价
        self.assertGreater(result['volume'], 0)  # 成交量
        self.assertTrue(result['should_poll'])  # 盘中应该轮询

        # 验证缓存被调用
        mock_set_cache.assert_called()

    def test_trading_phase_with_cache(self):
        """测试盘中时段K线计算（有缓存）"""
        symbol = '000001.SZ'
        test_time = pd.Timestamp(2025, 12, 16, 14, 30, 0)

        # Mock缓存数据
        cached_data = {
            'date': '2025-12-16',
            'open': 10.0,
            'high': 10.8,
            'low': 9.8,
            'close': 10.5,
            'volume': 10000
        }

        # Mock akshare分钟数据
        mock_minute_df = pd.DataFrame({
            '时间': ['2025-12-16 14:30:00'],
            '开盘': [10.5],
            '收盘': [10.7],
            '最高': [11.0],  # 新高
            '最低': [10.4],
            '成交量': [200],
            '成交额': [2100],
            '振幅': [0.6],
            '涨跌幅': [1.47],
            '涨跌额': [0.15],
            '换手率': [0.2]
        })

        with patch.object(self.provider, '_get_from_memory_cache', return_value=cached_data):
            with patch.object(self.provider, '_set_to_memory_cache_obj') as mock_update_cache:
                with patch.object(self.provider, '_map_to_akshare', return_value='000001'):
                    with patch.object(self.provider.ak, 'stock_zh_a_hist_min_em', return_value=mock_minute_df):
                        result = self.provider._get_today_k_column(symbol, test_time)

        # 验证结果
        self.assertEqual(result['date'], '2025-12-16')
        self.assertEqual(result['open'], 10.0)  # 复用缓存的开盘价
        self.assertEqual(result['high'], 11.0)  # 取更大值
        self.assertEqual(result['low'], 9.8)  # 取更小值（缓存中的更低）
        self.assertEqual(result['close'], 10.7)  # 最新分钟数据的收盘价
        self.assertTrue(result['should_poll'])

        # 验证缓存更新
        mock_update_cache.assert_called()

    def test_before_open_phase(self):
        """测试盘前时段（集合竞价）"""
        symbol = '000001.SZ'
        test_time = pd.Timestamp(2025, 12, 16, 9, 20, 0)  # 集合竞价时间

        # Mock盘口数据（买一价作为集合竞价参考）
        mock_bids = [
            OrderBookLevel(price=10.15, volume=50000),
            OrderBookLevel(price=10.14, volume=30000)
        ]
        mock_asks = [
            OrderBookLevel(price=10.16, volume=40000)
        ]

        with patch.object(self.provider, '_fetch_realtime_order_book', return_value=(mock_bids, mock_asks)):
            result = self.provider._get_today_k_column(symbol, test_time)

        # 验证结果
        self.assertEqual(result['date'], '2025-12-16')
        self.assertEqual(result['open'], 10.15)  # 买一价
        self.assertEqual(result['high'], 10.15)
        self.assertEqual(result['low'], 10.15)
        self.assertEqual(result['close'], 10.15)
        self.assertEqual(result['volume'], 0)  # 盘前无成交量
        self.assertTrue(result['should_poll'])  # 盘前应该轮询

    def test_after_close_phase(self):
        """测试盘后时段"""
        symbol = '000001.SZ'
        test_time = pd.Timestamp(2025, 12, 16, 16, 0, 0)  # 盘后时间

        result = self.provider._get_today_k_column(symbol, test_time)

        # 验证结果：盘后返回空数据，不轮询
        self.assertIsNone(result['date'])  # 盘后返回None
        self.assertIsNone(result['open'])
        self.assertIsNone(result['high'])
        self.assertIsNone(result['low'])
        self.assertIsNone(result['close'])
        self.assertEqual(result['volume'], 0)
        self.assertFalse(result['should_poll'])  # 盘后不轮询

    def test_no_intraday_data(self):
        """测试获取分时数据失败"""
        symbol = '000001.SZ'
        test_time = pd.Timestamp(2025, 12, 16, 10, 30, 0)

        # Mock空的分时数据
        mock_intraday = IntradayData(
            symbol=symbol,
            name='平安银行',
            current_price=10.3,
            yesterday_close=10.2,
            change=0.1,
            change_percent=0.98,
            ticks=[],  # 空ticks
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2025-12-16'),
            order_book_message='',
            trade_records_message='',
            is_index=False,
            should_poll=True
        )

        with patch.object(self.provider, 'get_intraday_data', return_value=mock_intraday):
            with patch.object(self.provider, '_get_from_memory_cache', return_value=None):
                result = self.provider._get_today_k_column(symbol, test_time)

        # 验证结果
        self.assertEqual(result['date'], '2025-12-16')
        self.assertIsNone(result['open'])  # 无数据时返回None
        self.assertTrue(result['should_poll'])  # 盘中仍然应该轮询

    def test_akshare_api_failure(self):
        """测试akshare API调用失败"""
        symbol = '000001.SZ'
        test_time = pd.Timestamp(2025, 12, 16, 10, 30, 0)

        # Mock分时数据
        mock_ticks = [
            IntradayTickRecord(time='09:30', price=10.0, volume=1000, avg_price=10.0)
        ]
        mock_intraday = IntradayData(
            symbol=symbol,
            name='平安银行',
            current_price=10.0,
            yesterday_close=10.2,
            change=-0.2,
            change_percent=-1.96,
            ticks=mock_ticks,
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2025-12-16'),
            order_book_message='',
            trade_records_message='',
            is_index=False,
            should_poll=True
        )

        # Mock缓存数据
        cached_data = {
            'date': '2025-12-16',
            'open': 10.0,
            'high': 10.2,
            'low': 9.9,
            'close': 10.0,
            'volume': 5000
        }

        with patch.object(self.provider, 'get_intraday_data', return_value=mock_intraday):
            with patch.object(self.provider, '_get_from_memory_cache', return_value=cached_data):
                with patch.object(self.provider, '_map_to_akshare', return_value='000001'):
                    # Mock akshare返回None（API失败）
                    with patch.object(self.provider.ak, 'stock_zh_a_hist_min_em', return_value=None):
                        result = self.provider._get_today_k_column(symbol, test_time)

        # 验证结果：应该返回缓存数据
        self.assertEqual(result['date'], '2025-12-16')
        self.assertEqual(result['open'], 10.0)
        self.assertTrue(result['should_poll'])

    def test_cross_market_symbols(self):
        """测试不同市场的股票代码"""
        test_cases = [
            ('000001.SZ', pd.Timestamp(2025, 12, 16, 10, 30, 0), MarketCode.CN),  # 深圳
            ('600000.SH', pd.Timestamp(2025, 12, 16, 10, 30, 0), MarketCode.CN),  # 上海
            ('000300.SH', pd.Timestamp(2025, 12, 16, 10, 30, 0), MarketCode.CN),  # 指数
        ]

        for symbol, test_time, expected_market in test_cases:
            with self.subTest(symbol=symbol):
                # Mock分时数据
                mock_ticks = [IntradayTickRecord(time='10:30', price=100.0, volume=1000, avg_price=100.0)]
                mock_intraday = IntradayData(
                    symbol=symbol, name='测试', current_price=100.0, yesterday_close=99.0,
                    change=1.0, change_percent=1.01, ticks=mock_ticks,
                    order_book_bids=[], order_book_asks=[], trade_records=[],
                    trade_date=pd.Timestamp(test_time.strftime('%Y-%m-%d')),
                    order_book_message='', trade_records_message='',
                    is_index=True if '.' in symbol and symbol.startswith('00030') else False,
                    should_poll=True
                )

                with patch.object(self.provider, 'get_intraday_data', return_value=mock_intraday):
                    with patch.object(self.provider, '_get_from_memory_cache', return_value=None):
                        with patch.object(self.provider, '_set_to_memory_cache_obj'):
                            with patch.object(self.provider, '_map_to_akshare', return_value=symbol[:6]):
                                mock_df = pd.DataFrame({'时间': [test_time.strftime('%Y-%m-%d %H:%M:%S')],
                                                       '开盘': [100.0], '收盘': [100.0], '最高': [100.5],
                                                       '最低': [99.5], '成交量': [1000], '成交额': [100000],
                                                       '振幅': [1.0], '涨跌幅': [1.01], '涨跌额': [1.0], '换手率': [0.5]})
                                with patch.object(self.provider.ak, 'stock_zh_a_hist_min_em', return_value=mock_df):
                                    result = self.provider._get_today_k_column(symbol, test_time)

                # 验证基本结构
                self.assertIn('date', result)
                self.assertIn('open', result)
                self.assertIn('should_poll', result)


if __name__ == '__main__':
    unittest.main()
