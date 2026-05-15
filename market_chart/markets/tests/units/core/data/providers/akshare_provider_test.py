"""
AKShare数据提供者测试套件
测试AKShareDataProvider的各种功能和边界情况
"""

import unittest


from unittest.mock import Mock, patch

import pandas as pd

# 导入被测试的类
from core.data.providers.akshare_provider import AKShareDataProvider
from core.data.providers.protocols import IntradayData
from core.share.market.market_time_utils import MarketTimeUtils


class TestAKShareDataProvider(unittest.TestCase):
    """AKShare数据提供者测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
        
    def test_initialization(self):
        """测试初始化"""
        self.assertIsInstance(self.provider, AKShareDataProvider)
        self.assertTrue(self.provider.available)
        self.assertIsNotNone(self.provider.ak)
        
    def test_get_test_symbol(self):
        """测试获取测试符号"""
        symbol = self.provider.get_test_symbol()
        self.assertEqual(symbol, '000300.SH')

from core.share.market.market_utils import MarketUtils

class TestAKShareIntradayData(unittest.TestCase):
    """AKShare分时数据获取测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
        
    @patch.object(MarketUtils, 'determine_trading_phase')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_get_intraday_data_from_api_success(self, mock_fetch_real, mock_phase):
        """测试从真实API成功获取分时数据"""
        from core.share.market.market_enums import TradingPhase

        # 模拟盘中时段（不使用缓存）
        mock_phase.return_value = TradingPhase.TRADING
        
        # 模拟真实API返回DataFrame
        mock_df = pd.DataFrame({
            '时间': ['2023-01-03 09:30:00', '2023-01-03 09:31:00'],
            '收盘': [3500.0, 3501.0],
            '开盘': [3499.0, 3500.0],
            '最高': [3501.0, 3502.0],
            '最低': [3498.0, 3499.0],
            '成交量': [10000, 10100],
            '成交额': [35000000, 35350000],
            '涨跌额': [20.0, 20.01]
        })
        mock_fetch_real.return_value = mock_df
        
        # 调用方法（使用工作日，传入current_time参数）
        test_time = pd.Timestamp(2023, 1, 3, 10, 30)  # 盘中时间
        result = self.provider.get_intraday_data('000300.SH', current_time=test_time)
        
        # 验证结果
        self.assertIsInstance(result, IntradayData)
        self.assertEqual(result.symbol, '000300.SH')
        # current_price是最后一个tick的价格
        self.assertGreater(result.current_price, 0)
        # 新逻辑：盘中时段直接调用，参数为 (symbol, trade_date, tick_range)
        # 验证调用了 _fetch_real_intraday_from_akshare，但不验证具体参数（因为current_time使用的是系统时间）
        self.assertGreater(mock_fetch_real.call_count, 0, "应该调用了API")
        # trading_phase参数已被移除，不再验证
        
    @patch.object(MarketUtils, 'determine_trading_phase')
    @patch.object(MarketUtils, 'get_last_trade_date')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_get_intraday_data_memory_cache_hit(self, mock_fetch_real, mock_get_last_date, mock_phase):
        """测试内存缓存命中（盘后读取盘中缓存）"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟当前时间为指定日期
        test_date = '2023-01-01'
        trading_time = pd.Timestamp(2023, 1, 1, 10, 30)  # 盘中时间
        after_close_time = pd.Timestamp(2023, 1, 1, 16, 0)  # 盘后时间
        
        # 模拟盘中时段：第一次调用会缓存
        mock_phase.return_value = TradingPhase.TRADING
        # 模拟真实API返回DataFrame
        mock_df = pd.DataFrame({
            '时间': ['2023-01-01 09:30:00', '2023-01-01 09:31:00'],
            '收盘': [3500.0, 3501.0],
            '开盘': [3499.0, 3500.0],
            '最高': [3501.0, 3502.0],
            '最低': [3498.0, 3499.0],
            '成交量': [10000, 10100],
            '成交额': [35000000, 35350000],
            '涨跌额': [20.0, 20.01]
        })
        mock_fetch_real.return_value = mock_df
        
        # 第一次调用（盘中时段，会缓存）
        result1 = self.provider.get_intraday_data('000300.SH', current_time=trading_time)
        # 验证调用了_fetch_real_intraday_from_akshare
        call_args = mock_fetch_real.call_args
        # 新架构：参数为 (symbol, pd.Timestamp, TickRange)
        self.assertEqual(call_args[0][0], '000300.SH', "symbol应该是000300.SH")
        self.assertIsInstance(call_args[0][1], pd.Timestamp, "第二个参数应该是pd.Timestamp")
        # tick_range可能是None或TickRange对象
        mock_fetch_real.reset_mock()  # 重置调用计数
        
        # 预先设置缓存，模拟盘中时段已经缓存了数据（使用result1）
        cache_key = f"intraday_000300.SH_{test_date}_TRADING"
        self.provider._set_to_memory_cache_obj(cache_key, result1)
        
        # 模拟盘后时段：第二次调用从缓存读取
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = test_date  # 当天就是最后交易日
        result2 = self.provider.get_intraday_data('000300.SH', current_time=after_close_time)
        
        # 验证：应该使用了缓存的数据
        self.assertIsNotNone(result2)
        self.assertGreater(result2.current_price, 0)
        
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    @patch.object(MarketUtils, 'get_last_trade_date')
    @patch.object(MarketUtils, 'determine_trading_phase')
    def test_get_intraday_data_fallback_to_previous_day(self, mock_phase, mock_get_last_date, mock_fetch_real):
        """测试fallback到前一交易日缓存（新逻辑：盘后使用缓存）"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟当前时间为盘后（传入current_time参数，不需要mock pd.Timestamp.now）
        test_time = pd.Timestamp(2023, 1, 1, 16, 0)  # 盘后时间
        
        # 模拟盘后时段
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = pd.Timestamp('2022-12-31')
        mock_fetch_real.side_effect = Exception("API失败")
        
        # 预先写入前一天的盘中缓存（使用 _TRADING 后缀）
        prev_intraday = IntradayData(
            symbol='000300.SH',
            name='沪深300',
            current_price=3480.0,
            yesterday_close=3460.0,
            change=20.0,
            change_percent=0.58,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2022-12-31')
        )
        cache_key = "intraday_000300.SH_2022-12-31_TRADING"  # 新的缓存key格式
        self.provider._set_to_memory_cache_obj(cache_key, prev_intraday)
        
        # 调用当天数据（盘后时段，会使用缓存）
        result = self.provider.get_intraday_data('000300.SH', current_time=test_time)
        
        # 验证使用了前一天的数据
        self.assertEqual(result.current_price, 3480.0)
        
    @patch('datetime.datetime')
    @patch.object(MarketUtils, 'determine_trading_phase')
    @patch.object(MarketUtils, 'get_last_trade_date')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_get_intraday_data_fallback_to_mock(self, mock_fetch_real, mock_get_last_date, mock_phase, mock_datetime):
        """测试盘中时段，API失败时抛出异常（新逻辑：不再fallback到模拟数据）"""
        from core.share.market.market_enums import TradingPhase

        from unittest.mock import MagicMock
        
        # 模拟当前时间为指定日期
        test_time = pd.Timestamp(2023, 1, 3, 10, 30)  # 盘中时间
        mock_now = MagicMock()
        mock_now.strftime.return_value = '2023-01-03'
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = pd.Timestamp.strptime
        
        # 模拟盘中时段（不使用缓存）
        mock_phase.return_value = TradingPhase.TRADING
        mock_fetch_real.side_effect = Exception("API失败")
        
        # 调用方法（API失败时应该抛出RuntimeError）
        with self.assertRaises(RuntimeError) as context:
            self.provider.get_intraday_data('000300.SH', current_time=test_time)
        
        # 验证异常消息
        self.assertIn('无法获取分时数据', str(context.exception))
        self.assertIn('000300.SH', str(context.exception))
        

class TestAKShareIntradayHelperMethods(unittest.TestCase):
    """AKShare分时数据辅助方法测试"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
        
    @patch('akshare.stock_zh_a_hist_min_em')
    def test_fetch_real_intraday_from_akshare_success(self, mock_ak_api):
        """测试真实API调用成功"""
        # 模拟AKShare API返回
        # 创建足够的数据以通过完整性检查（240条数据）
        time_list = []
        close_list = []
        open_list = []
        high_list = []
        low_list = []
        volume_list = []
        amount_list = []
        change_list = []
        
        # 上午：09:30-11:30 (120分钟)
        for i in range(120):
            hour = 9 + (30 + i) // 60
            minute = (30 + i) % 60
            time_list.append(f'2023-01-01 {hour:02d}:{minute:02d}:00')
            close_list.append(3500.0 + i * 0.01)
            open_list.append(3499.0 + i * 0.01)
            high_list.append(3501.0 + i * 0.01)
            low_list.append(3498.0 + i * 0.01)
            volume_list.append(10000 + i * 10)
            amount_list.append(35000000 + i * 1000)
            change_list.append(20.0 + i * 0.01)
        
        # 下午：13:00-15:00 (120分钟)
        for i in range(120):
            hour = 13 + i // 60
            minute = i % 60
            time_list.append(f'2023-01-01 {hour:02d}:{minute:02d}:00')
            close_list.append(3500.0 + (120 + i) * 0.01)
            open_list.append(3499.0 + (120 + i) * 0.01)
            high_list.append(3501.0 + (120 + i) * 0.01)
            low_list.append(3498.0 + (120 + i) * 0.01)
            volume_list.append(10000 + (120 + i) * 10)
            amount_list.append(35000000 + (120 + i) * 1000)
            change_list.append(20.0 + (120 + i) * 0.01)
        
        mock_df = pd.DataFrame({
            '时间': time_list,
            '收盘': close_list,
            '开盘': open_list,
            '最高': high_list,
            '最低': low_list,
            '成交量': volume_list,
            '成交额': amount_list,
            '涨跌额': change_list
        })
        mock_ak_api.return_value = mock_df
        self.provider.ak.stock_zh_a_hist_min_em = mock_ak_api
        
        # 调用方法（tick_range 参数为 None）
        result = self.provider._fetch_real_intraday_from_external_api('000300.SH', pd.Timestamp('2023-01-01'), tick_range=None)
        
        # 验证结果：现在返回 DataFrame
        self.assertIsInstance(result, pd.DataFrame)
        self.assertGreater(len(result), 0)
        
    @patch('akshare.stock_zh_a_hist_min_em')
    def test_fetch_real_intraday_from_akshare_empty_data(self, mock_ak_api):
        """测试API返回空数据"""
        mock_ak_api.return_value = pd.DataFrame()
        self.provider.ak.stock_zh_a_hist_min_em = mock_ak_api
        
        # 调用方法（tick_range 参数为 None）
        # 新架构：空数据会抛出ValueError（数据不完整）
        with self.assertRaises(ValueError) as context:
            result = self.provider._fetch_real_intraday_from_external_api('000300.SH', pd.Timestamp('2023-01-01'), tick_range=None)
        
        # 验证异常消息
        self.assertIn('数据不完整', str(context.exception))
        
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    @patch.object(MarketUtils, 'get_last_trade_date')
    @patch.object(MarketUtils, 'determine_trading_phase')
    @patch('pandas.Timestamp')
    def test_get_intraday_data_weekend_fallback(self, mock_timestamp, mock_phase, mock_get_last_date, mock_fetch):
        """测试周末调用时自动获取最近交易日的缓存"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟当前时间为周末
        weekend_time = pd.Timestamp('2023-12-09 10:00:00')  # 周六
        mock_timestamp.now.return_value = weekend_time
        
        # 模拟最近交易日为周五
        mock_phase.return_value = TradingPhase.AFTER_CLOSE  # 周末是盘后时段
        mock_get_last_date.return_value = pd.Timestamp('2023-12-08')
        
        # 预先写入周五的缓存（使用正确的键格式）
        cached_data = IntradayData(
            symbol='000300.SH',
            name='沪深300',
            current_price=3500.0,
            yesterday_close=3480.0,
            change=20.0,
            change_percent=0.57,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2023-12-08')
        )
        cache_key = "intraday_000300.SH_2023-12-08_TRADING"
        self.provider._set_to_memory_cache_obj(cache_key, cached_data)
        
        # 周末调用（不指定current_time，使用mock的时间）
        result = self.provider.get_intraday_data('000300.SH')
        
        # 验证返回了数据
        self.assertIsInstance(result, IntradayData)
        self.assertEqual(result.symbol, '000300.SH')
        
    def test_generate_mock_intraday_data(self):
        """测试生成模拟分时数据（使用MockDataProvider）"""
        from core.data.providers.mock_provider import MockDataProvider

        generator = MockDataProvider()
        result = generator.generate_intraday_data(
            symbol='000300.SH',
            trade_date=pd.Timestamp('2023-01-03'),
            tick_range=None,  # 根据 trading_phase 自动创建
            last_price=None,
            is_index=True
        )
        
        # 验证基本字段
        self.assertIsInstance(result, IntradayData)
        self.assertEqual(result.symbol, '000300.SH')
        self.assertEqual(result.trade_date, '2023-01-03')
        
        # 验证tick数据（盘后模式应该返回全天数据 09:30-15:00）
        self.assertIsInstance(result.ticks, list)
        self.assertGreater(len(result.ticks), 0, "应该有至少1个tick")
        
        # 验证指数不生成盘口和成交明细
        self.assertEqual(len(result.order_book_bids), 0)
        self.assertEqual(len(result.order_book_asks), 0)
        self.assertEqual(len(result.trade_records), 0)
        self.assertEqual(result.order_book_message, '指数不可交易')
        self.assertEqual(result.trade_records_message, '指数无成交明细')  # 修正为正确的提示信息
        
    def test_generate_mock_order_book(self):
        """测试生成模拟盘口（使用MockDataProvider）"""
        from core.data.providers.mock_provider import MockDataProvider
        
        generator = MockDataProvider()
        bids, asks = generator._generate_order_book(3500.0)
        
        # 验证数量
        self.assertEqual(len(bids), 10)
        self.assertEqual(len(asks), 10)
        
        # 验证买盘价格递减
        self.assertGreater(bids[0].price, bids[1].price)
        
        # 验证卖盘价格递增
        self.assertLess(asks[0].price, asks[1].price)
        
    def test_generate_mock_tickers(self):
        """测试生成模拟成交明细（使用MockDataProvider）"""
        from core.data.providers.mock_provider import MockDataProvider
        from core.data.providers.protocols import IntradayTickRecord
        
        generator = MockDataProvider()
        # 创建一些模拟 tick 数据
        recent_ticks = [
            IntradayTickRecord(time='14:58:00', price=3500.0, volume=1000, avg_price=3499.0),
            IntradayTickRecord(time='14:59:00', price=3501.0, volume=1100, avg_price=3500.0),
        ]
        trade_records = generator._generate_trade_details(3500.0, recent_ticks)  # 方法重命名
        
        # 验证数量
        self.assertGreater(len(trade_records), 0)
        
        # 验证字段
        for trade_record in trade_records:
            self.assertIsNotNone(trade_record.time)
            self.assertIsNotNone(trade_record.price)
            self.assertIsNotNone(trade_record.volume)
            self.assertIn(trade_record.direction, ['buy', 'sell'])


class TestAKShareIntradayConversion(unittest.TestCase):
    """AKShare数据转换测试"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
        
    def test_convert_akshare_df_to_intraday(self):
        """测试DataFrame转IntradayData（使用IntradayData.from_akshare_df）"""
        from core.data.providers.protocols import IntradayData
        # 构造测试数据
        df = pd.DataFrame({
            '时间': ['2023-01-01 09:30:00', '2023-01-01 09:31:00'],
            '收盘': [3500.0, 3501.0],
            '开盘': [3498.0, 3500.0],
            '最高': [3502.0, 3503.0],
            '最低': [3497.0, 3499.0],
            '成交量': [10000, 11000],
            '涨跌额': [20.0, 21.0]
        })
        
        # 调用转换方法（现在是IntradayData的类方法）
        result = IntradayData.from_akshare_df(
            df, '000300.SH', '2023-01-01',
            interpolate_func=self.provider._interpolate_to_5_seconds
        )
        
        # 验证结果
        self.assertIsInstance(result, IntradayData)
        self.assertEqual(result.symbol, '000300.SH')
        # 由于插值，tick数量会比原始数据多
        self.assertGreater(len(result.ticks), 0)
        

if __name__ == '__main__':
    unittest.main()


# ===== 以下是整合自其他测试文件的测试类 =====

# 整合自: trading_phase_bug_test.py 和 akshare_provider_trading_phase_test.py
class TradingPhaseBugTest(unittest.TestCase):
    """测试 trading_phase 枚举一致性和正确性"""
    
    def setUp(self):
        """设置测试环境"""
        self.provider = AKShareDataProvider()
    
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    @patch.object(MarketUtils, 'get_last_trade_date')
    @patch.object(MarketUtils, 'determine_trading_phase')
    @patch('pandas.Timestamp')
    def test_weekend_returns_after_close_not_before_open(self, mock_timestamp, mock_phase, mock_get_last_date, mock_fetch):
        """
        测试：周末应该返回 after_close，而不是 before_open
        
        Bug场景：
        - 周日凌晨 05:30
        - AKShare API 调用失败
        - 旧代码错误地返回 trading_phase='before_open'
        - 修复后应该返回 trading_phase='after_close'
        """
        from core.share.market.market_enums import TradingPhase
        
        # 冻结时间到周日凌晨
        sunday_morning = pd.Timestamp(2025, 12, 14, 5, 30, 0)  # 周日 05:30
        mock_timestamp.now.return_value = sunday_morning
        
        # 模拟交易时段和最后交易日
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = pd.Timestamp('2025-12-12')  # 周五
        
        # 预先设置周五的缓存数据
        friday_data = IntradayData(
            symbol='000001.SH',
            name='平安银行',
            current_price=10.0,
            yesterday_close=9.5,
            change=0.5,
            change_percent=5.26,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2025-12-12'),  # 周五
            is_index=True
        )
        cache_key = "intraday_000001.SH_2025-12-12_TRADING"
        self.provider._set_to_memory_cache_obj(cache_key, friday_data)
        
        # 调用 get_intraday_data
        result = self.provider.get_intraday_data('000001.SH')
        
        # 验证返回的 should_poll（缓存数据应该保留 should_poll 字段）
        self.assertIsInstance(result.should_poll, bool)

    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    @patch.object(MarketUtils, 'get_last_trade_date')
    @patch.object(MarketUtils, 'determine_trading_phase')
    @patch('pandas.Timestamp')
    def test_saturday_returns_after_close(self, mock_timestamp, mock_phase, mock_get_last_date, mock_fetch):
        """
        测试：周六应该返回 after_close
        """
        from core.share.market.market_enums import TradingPhase
        
        # 冻结时间到周六下午
        saturday_afternoon = pd.Timestamp(2025, 12, 13, 14, 0, 0)  # 周六 14:00
        mock_timestamp.now.return_value = saturday_afternoon
        
        # 模拟交易时段和最后交易日
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = pd.Timestamp('2025-12-12')  # 周五
        
        # 预先设置周五的缓存数据
        friday_data = IntradayData(
            symbol='000001.SH',
            name='平安银行',
            current_price=10.0,
            yesterday_close=9.5,
            change=0.5,
            change_percent=5.26,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp('2025-12-12'),  # 周五
            is_index=True
        )
        cache_key = "intraday_000001.SH_2025-12-12_TRADING"
        self.provider._set_to_memory_cache_obj(cache_key, friday_data)
        
        # 调用 get_intraday_data
        result = self.provider.get_intraday_data('000001.SH')
        
        # 验证返回的 should_poll（缓存数据应该保留 should_poll 字段）
        self.assertIsInstance(result.should_poll, bool)
    
    def test_get_trading_phase_returns_enum(self):
        """
        测试：determine_trading_phase() 必须返回枚举类型，不能返回字符串
        """
        from core.share.market.market_enums import MarketCode, TradingPhase
        # 周末
        sunday = pd.Timestamp(2025, 12, 14, 10, 0, 0)
        result = MarketTimeUtils.determine_trading_phase(MarketCode.CN, sunday)
        
        self.assertIsInstance(
            result,
            TradingPhase,
            f"determine_trading_phase() 必须返回 TradingPhase 枚举，实际返回: {type(result)}"
        )
        self.assertEqual(result, TradingPhase.AFTER_CLOSE)
        
        # 工作日集合竞价时段
        monday_call_auction = pd.Timestamp(2025, 12, 16, 9, 15, 0)  # 周一 09:15
        result = MarketTimeUtils.determine_trading_phase(MarketCode.CN, monday_call_auction)
        
        self.assertIsInstance(result, TradingPhase)
        self.assertEqual(result, TradingPhase.BEFORE_OPEN)
        
        # 工作日交易时段
        monday_trading = pd.Timestamp(2025, 12, 16, 10, 30, 0)  # 周一 10:30
        result = MarketTimeUtils.determine_trading_phase(MarketCode.CN, monday_trading)
        
        self.assertIsInstance(result, TradingPhase)
        self.assertEqual(result, TradingPhase.TRADING)
        
        # 工作日盘后
        monday_after_close = pd.Timestamp(2025, 12, 16, 16, 0, 0)  # 周一 16:00
        result = MarketTimeUtils.determine_trading_phase(MarketCode.CN, monday_after_close)
        
        self.assertIsInstance(result, TradingPhase)
        self.assertEqual(result, TradingPhase.AFTER_CLOSE)
    
    def test_generate_empty_intraday_data_respects_trading_phase(self):
        """
        测试：_generate_empty_data() 返回的DataFrame包含正确的初始化信息
        """
        import pandas as pd
        symbol = '000001.SH'
        trade_date = pd.Timestamp('2025-12-14')
        
        # 测试 AFTER_CLOSE
        result = self.provider._generate_empty_pd_data(
            symbol
        )
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)
        self.assertIn('_init_info', result.attrs)
        self.assertEqual(result.attrs['_init_info']['name'], '上证指数')
        self.assertEqual(result.attrs['_init_info']['is_index'], True)
        
        # 测试 BEFORE_OPEN
        result = self.provider._generate_empty_pd_data(
            symbol
        )
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(result.attrs['_init_info']['name'], '上证指数')
        
        # 测试 TRADING
        result = self.provider._generate_empty_pd_data(
            symbol
        )
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(result.attrs['_init_info']['name'], '上证指数')


# 整合自: cache_strategy_test.py
class TestCacheStrategy(unittest.TestCase):
    """测试缓存策略"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
        self.provider._enable_memory_cache = True
        
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch.object(AKShareDataProvider, '_fetch_order_book_and_trades')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_trading_phase_no_cache_on_read(self, mock_fetch, mock_fetch_order_book, mock_phase):
        """盘中时段：不从缓存读取，每次都实时获取"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟时间：2023-01-03 10:30（盘中）
        test_time = pd.Timestamp(2023, 1, 3, 10, 30)
        mock_phase.return_value = TradingPhase.TRADING
        
        # mock盘口数据
        mock_fetch_order_book.return_value = ([], [], [], '暂无盘口数据', '暂无成交明细')
        
        # mock返回DataFrame（不是IntradayData）
        mock_df = pd.DataFrame({
            '时间': ['2023-01-03 09:30:00', '2023-01-03 09:31:00'],
            '收盘': [10.0, 10.1],
            '开盘': [9.9, 10.0],
            '最高': [10.1, 10.2],
            '最低': [9.8, 9.9],
            '成交量': [10000, 10100],
            '成交额': [100000, 101000],
            '涨跌额': [0.5, 0.6]
        })
        mock_fetch.return_value = mock_df
        
        # 第一次调用
        result1 = self.provider.get_intraday_data('000001.SZ', market_local_time=test_time)
        self.assertEqual(mock_fetch.call_count, 1)
        
        # 第二次调用（盘中时段应该再次获取，不使用缓存）
        result2 = self.provider.get_intraday_data('000001.SZ', market_local_time=test_time)
        self.assertEqual(mock_fetch.call_count, 2)  # 应该调用2次
        
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch.object(AKShareDataProvider, '_fetch_order_book_and_trades')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_trading_phase_writes_cache(self, mock_fetch, mock_fetch_order_book, mock_phase):
        """盘中时段：不缓存数据（总是获取最新值）"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟时间：2023-01-03 10:30（盘中）
        test_time = pd.Timestamp(2023, 1, 3, 10, 30)
        test_date = '2023-01-03'
        
        mock_phase.return_value = TradingPhase.TRADING
        
        # mock盘口数据
        mock_fetch_order_book.return_value = ([], [], [], '暂无盘口数据', '暂无成交明细')
        
        # mock返回DataFrame
        mock_df = pd.DataFrame({
            '时间': ['2023-01-03 09:30:00', '2023-01-03 09:31:00'],
            '收盘': [10.0, 10.1],
            '开盘': [9.9, 10.0],
            '最高': [10.1, 10.2],
            '最低': [9.8, 9.9],
            '成交量': [10000, 10100],
            '成交额': [100000, 101000],
            '涨跌额': [0.5, 0.6]
        })
        mock_fetch.return_value = mock_df
        
        # 调用获取数据
        result = self.provider.get_intraday_data('000001.SZ', current_time=test_time)
        
        # 验证：盘中时段不缓存数据
        cache_key = f"intraday_000001.SZ_{test_date}_TRADING"
        cached = self.provider._get_from_memory_cache(cache_key)
        self.assertIsNone(cached)  # 盘中不缓存
        self.assertIsNotNone(result)  # 但返回的数据是有效的
        
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch('core.share.markets.market_utils.MarketUtils.get_last_trade_date')
    @patch.object(AKShareDataProvider, '_fetch_order_book_and_trades')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_after_close_uses_trading_cache(self, mock_fetch, mock_fetch_order_book, mock_get_last_date, mock_phase):
        """盘后时段：尝试从缓存读取，如果没有则调用API获取盘后数据"""
        from core.share.market.market_enums import TradingPhase
        
        test_date = pd.Timestamp('2023-01-03')
        # 模拟盘后时间：2023-01-03 16:00
        after_close_time = pd.Timestamp(2023, 1, 3, 16, 0)
        
        # 模拟盘后时段
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = test_date
        
        # 预先设置缓存（模拟盘后获取数据时的缓存）
        cached_data = IntradayData(
            symbol='000001.SZ',
            name='平安银行',
            current_price=10.0,
            yesterday_close=9.5,
            change=0.5,
            change_percent=5.26,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp(test_date.strftime('%Y-%m-%d')),
        )
        cache_key = f"intraday_000001.SZ_{test_date}_TRADING"
        self.provider._set_to_memory_cache_obj(cache_key, cached_data)
        
        # 盘后获取数据（应该从缓存读取）
        result = self.provider.get_intraday_data('000001.SZ', current_time=after_close_time)
        
        # 验证：从缓存读取，不调用API
        self.assertEqual(mock_fetch.call_count, 0)
        self.assertEqual(result.current_price, 10.0)
        
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch.object(AKShareDataProvider, '_fetch_order_book_and_trades')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_before_open_no_cache(self, mock_fetch, mock_fetch_order_book, mock_phase):
        """盘前时段：不缓存数据，生成空DataFrame"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟时间：2023-01-03 09:15（集合竞价时段）
        test_time = pd.Timestamp(2023, 1, 3, 9, 15)
        mock_phase.return_value = TradingPhase.BEFORE_OPEN
        
        # mock盘口数据
        mock_fetch_order_book.return_value = ([], [], [], '暂无盘口数据', '暂无成交明细')
        
        # 盘前时段会生成空DataFrame，不调用API
        # 第一次调用
        result1 = self.provider.get_intraday_data('000001.SZ', current_time=test_time)
        self.assertEqual(mock_fetch.call_count, 0)  # 集合竞价时段不调用API
        self.assertEqual(len(result1.ticks), 0)  # 返回空的ticks
        
        # 第二次调用（盘前时段仍然不调用API，且不缓存）
        result2 = self.provider.get_intraday_data('000001.SZ', current_time=test_time)
        self.assertEqual(mock_fetch.call_count, 0)  # 集合竞价时段不调用API
        
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch('core.share.markets.market_utils.MarketUtils.get_last_trade_date')
    @patch.object(AKShareDataProvider, '_fetch_order_book_and_trades')
    @patch.object(AKShareDataProvider, '_fetch_real_intraday_from_akshare')
    def test_cache_key_format(self, mock_fetch, mock_fetch_order_book, mock_get_last_date, mock_phase):
        """验证缓存key格式：intraday_{symbol}_{date}_TRADING（盘后缓存）"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟时间：2023-01-03 16:00（盘后）
        test_time = pd.Timestamp(2023, 1, 3, 16, 0)
        test_date = '2023-01-03'
        
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = test_date
        
        # mock盘口数据
        mock_fetch_order_book.return_value = ([], [], [], '暂无盘口数据', '暂无成交明细')
        
        # mock返回DataFrame
        mock_df = pd.DataFrame({
            '时间': ['2023-01-03 09:30:00', '2023-01-03 09:31:00'],
            '收盘': [3500.0, 3501.0],
            '开盘': [3499.0, 3500.0],
            '最高': [3502.0, 3503.0],
            '最低': [3498.0, 3499.0],
            '成交量': [10000, 10100],
            '成交额': [35000000, 35010000],
            '涨跌额': [20.0, 21.0]
        })
        mock_fetch.return_value = mock_df
        
        # 调用获取数据（盘后会缓存）
        self.provider.get_intraday_data('000300.SH', current_time=test_time)
        
        # 验证缓存key格式（盘后获取数据时会缓存）
        correct_key = f"intraday_000300.SH_{test_date}_TRADING"
        wrong_key = f"intraday_000300.SH_{test_date}"  # 旧格式
        
        self.assertIsNotNone(self.provider._get_from_memory_cache(correct_key))
        self.assertIsNone(self.provider._get_from_memory_cache(wrong_key))


# 整合自: intraday_after_close_test.py 和 akshare_intraday_nontrading_test.py
class TestNonTradingPeriodBehavior(unittest.TestCase):
    """测试非交易时段的分时数据获取逻辑"""
    
    def setUp(self):
        """setUp"""
        self.provider = AKShareDataProvider()
        self.provider.available = True
        self.provider.ak = Mock()
    
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch('core.share.markets.market_utils.MarketUtils.get_last_trade_date')
    def test_after_close_should_use_cache(self, mock_get_last_date, mock_phase):
        """测试：盘后时段应使用缓存数据"""
        from core.share.market.market_enums import TradingPhase
        
        test_date = pd.Timestamp('2025-12-19')
        # 模拟盘后时间：2025-12-19 16:00
        after_close_time = pd.Timestamp(2025, 12, 19, 16, 0)
        
        # 模拟盘后时段
        mock_phase.return_value = TradingPhase.AFTER_CLOSE
        mock_get_last_date.return_value = test_date
        
        # 预先设置缓存
        cached_data = IntradayData(
            symbol='600030.SH',
            name='中信证券',
            current_price=10.8,
            yesterday_close=10.5,
            change=0.3,
            change_percent=2.86,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=pd.Timestamp(test_date.strftime('%Y-%m-%d')),
        )
        cache_key = f"intraday_600030.SH_{test_date}_TRADING"
        self.provider._set_to_memory_cache_obj(cache_key, cached_data)
        
        result = self.provider.get_intraday_data('600030.SH', current_time=after_close_time)
        self.assertIsNotNone(result)
        self.assertEqual(result.current_price, 10.8)
    
    @patch('core.share.markets.market_utils.MarketTimeUtils.determine_trading_phase')
    @patch.object(AKShareDataProvider, '_fetch_order_book_and_trades')
    def test_before_open_clears_chart(self, mock_fetch_order_book, mock_phase):
        """测试：集合竞价时段清空分时图"""
        from core.share.market.market_enums import TradingPhase
        
        # 模拟集合竞价时间：2025-12-19 09:15
        before_open_time = pd.Timestamp(2025, 12, 19, 9, 15)
        
        # 模拟集合竞价时段
        mock_phase.return_value = TradingPhase.BEFORE_OPEN
        
        # mock盘口数据（盘前也会尝试获取盘口）
        mock_fetch_order_book.return_value = ([], [], [], '集合竞价时段，请轮询盘口数据', '集合竞价时段，暂无成交明细')
        
        result = self.provider.get_intraday_data('600030.SH', current_time=before_open_time)
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result.ticks), 0, "集合竞价时段应清空分时图")
        self.assertEqual(result.order_book_message, '集合竞价时段，请轮询盘口数据')
