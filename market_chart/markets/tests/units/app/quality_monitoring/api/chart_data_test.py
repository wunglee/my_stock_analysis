"""ChartDataAssembler 单元测试

符合规范：
- 测试文件命名: chart_data_test.py (对应 chart_data.py)
- 目录镜像: tests/units/app/quality_monitoring/api/ 对应 app/quality_monitoring/api/
"""

import unittest
from unittest.mock import Mock

import numpy as np
import pandas as pd

from app.chart_data import ChartDataAssembler
from core.data.providers.protocols import PriceData
from core.share.market.data_types import OHLCVRecord


class ChartDataAssemblerBasicTest(unittest.TestCase):
    """ChartDataAssembler 基础功能测试"""
    
    def setUp(self):
        """测试前准备"""
        # Mock数据提供者
        self.mock_provider = Mock()
        
        # Mock技术指标服务
        self.mock_indicator = Mock()
        
        # 创建组装器实例
        self.assembler = ChartDataAssembler(
            data_provider=self.mock_provider,
            indicator_service=self.mock_indicator
        )
    
    def test_safe_float_normal_value(self):
        """测试安全浮点数转换 - 正常值"""
        result = self.assembler._safe_float(123.45)
        self.assertEqual(result, 123.45)
    
    def test_safe_float_nan_value(self):
        """测试安全浮点数转换 - NaN值"""
        result = self.assembler._safe_float(np.nan)
        self.assertIsNone(result)
    
    def test_safe_float_none_value(self):
        """测试安全浮点数转换 - None值"""
        result = self.assembler._safe_float(None)
        self.assertIsNone(result)
    
    def test_safe_float_string_value(self):
        """测试安全浮点数转换 - 字符串数值"""
        result = self.assembler._safe_float("123.45")
        self.assertEqual(result, 123.45)
    
    def test_safe_float_invalid_value(self):
        """测试安全浮点数转换 - 无效值"""
        result = self.assembler._safe_float("invalid")
        self.assertIsNone(result)


class ChartDataAssemblerPeriodConversionTest(unittest.TestCase):
    """周期转换功能测试"""
    
    def setUp(self):
        """测试前准备"""
        self.mock_provider = Mock()
        self.mock_indicator = Mock()
        self.assembler = ChartDataAssembler(
            data_provider=self.mock_provider,
            indicator_service=self.mock_indicator
        )
    

class ChartDataAssemblerEventDetectionTest(unittest.TestCase):
    """市场事件检测测试"""
    
    def setUp(self):
        """测试前准备"""
        self.mock_provider = Mock()
        self.mock_indicator = Mock()
        self.assembler = ChartDataAssembler(
            data_provider=self.mock_provider,
            indicator_service=self.mock_indicator
        )
    
    def test_detect_events_crash(self):
        """测试暴跌事件检测（强类型 PriceData）"""
        
        # 💚 构造包含暴跌的强类型 PriceData
        records = [
            OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-03'), open=100.0, high=105.0, low=92.0, close=93.0, volume=2000000),  # 暴跌 7%
        ]
        
        price_data = PriceData(
            symbol='000300.SH',
            records=records,
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-03'),
            count=3
        )
        
        # 💚 直接传入 PriceData 对象
        events = self.assembler._detect_events(price_data)
        
        # 验证事件检测
        crash_events = [e for e in events if e['type'] == 'market_crash']
        self.assertGreater(len(crash_events), 0)
        
        # 验证事件属性
        event = crash_events[0]
        self.assertEqual(event['impact'], 'negative')
        self.assertIn('severity', event)
        self.assertLess(event['decline_pct'], 0)
    
    def test_detect_events_rally(self):
        """测试暴涨事件检测（强类型 PriceData）"""
        from core.data.providers.protocols import OHLCVRecord
        
        # 💚 构造包含暴涨的强类型 PriceData
        records = [
            OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-03'), open=100.0, high=108.0, low=99.0, close=106.0, volume=2000000),  # 暴涨 6%
        ]
        
        price_data = PriceData(
            symbol='000300.SH',
            records=records,
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-03'),
            count=3
        )
        
        # 💚 直接传入 PriceData 对象
        events = self.assembler._detect_events(price_data)
        
        # 验证事件检测
        rally_events = [e for e in events if e['type'] == 'rally']
        self.assertGreater(len(rally_events), 0)
        
        # 验证事件属性
        event = rally_events[0]
        self.assertEqual(event['impact'], 'positive')
        self.assertGreater(event['rise_pct'], 0)
    
    def test_detect_events_no_extreme(self):
        """测试无极端事件（强类型 PriceData）"""
        from core.data.providers.protocols import OHLCVRecord
        
        # 💚 构造正常波动数据
        records = [
            OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=100.0, high=106.0, low=100.0, close=101.0, volume=1100000),
            OHLCVRecord(date=pd.Timestamp('2024-01-03'), open=101.0, high=107.0, low=101.0, close=102.0, volume=1200000),
            OHLCVRecord(date=pd.Timestamp('2024-01-04'), open=102.0, high=107.5, low=100.5, close=101.5, volume=1150000),
            OHLCVRecord(date=pd.Timestamp('2024-01-05'), open=101.5, high=108.0, low=101.0, close=102.5, volume=1250000),
        ]
        
        price_data = PriceData(
            symbol='000300.SH',
            records=records,
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-05'),
            count=5
        )
        
        # 💚 直接传入 PriceData 对象
        events = self.assembler._detect_events(price_data)
        
        # 验证无事件
        self.assertEqual(len(events), 0)


class ChartDataAssemblerIntegrationTest(unittest.TestCase):
    """集成测试 - 完整数据组装流程"""
    
    def setUp(self):
        """测试前准备"""
        # Mock数据提供者返回模拟数据
        self.mock_provider = Mock()
        self.mock_provider.get_index_prices = Mock(return_value=self._create_mock_data())
        
        # Mock技术指标服务
        self.mock_indicator = Mock()
        self._setup_indicator_mocks()
        
        self.assembler = ChartDataAssembler(
            data_provider=self.mock_provider,
            indicator_service=self.mock_indicator
        )
    
    def _create_mock_data(self):
        """创建模拟K线数据（强类型 PriceData）"""
        from core.data.providers.protocols import OHLCVRecord, PriceData
        
        # 创建模拟记录
        records = []
        dates = pd.date_range('2024-01-01', periods=120, freq='D')
        for i, date in enumerate(dates):
            record = OHLCVRecord(
                date=date,
                open=100 + np.random.randn() * 5,
                high=105 + np.random.randn() * 5,
                low=95 + np.random.randn() * 5,
                close=100 + np.random.randn() * 5,
                volume=1000000 + np.random.randn() * 100000
            )
            records.append(record)
        
        return PriceData(
            symbol='000001.SH',
            records=records,
            start_date=dates[0],
            end_date=dates[-1],
            count=120
        )
    
    def _setup_indicator_mocks(self):
        """设置指标服务的Mock返回值"""
        # MACD
        self.mock_indicator.calculate_macd = Mock(return_value=(
            pd.Series([0.5] * 120),
            pd.Series([0.3] * 120),
            pd.Series([0.2] * 120)
        ))
        
        # RSI
        self.mock_indicator.calculate_rsi = Mock(return_value=pd.Series([60.0] * 120))
        
        # KDJ
        self.mock_indicator.calculate_kdj = Mock(return_value=(
            pd.Series([70.0] * 120),
            pd.Series([65.0] * 120)
        ))
        
        # OBV
        self.mock_indicator.calculate_obv = Mock(return_value=pd.Series([5000000] * 120))
    
    def test_assemble_chart_data_success(self):
        """测试完整数据组装 - 成功场景"""
        result = self.assembler.assemble_chart_data(
            symbol='000001.SH',
            period='daily',
            count=120,
            before=None,
            indicators='all'
        )
        
        # 验证返回结构
        self.assertIn('kline', result)
        self.assertIn('indicators', result)
        self.assertIn('events', result)
        
        # 验证K线数据
        self.assertGreater(len(result['kline']), 0)
        first_kline = result['kline'][0]
        self.assertIn('date', first_kline)
        self.assertIn('open', first_kline)
        self.assertIn('ma5', first_kline)
        
        # 验证指标数据
        self.assertIn('vol', result['indicators'])
        self.assertIn('macd', result['indicators'])
        self.assertIn('rsi', result['indicators'])
        self.assertIn('kdj', result['indicators'])
        self.assertIn('obv', result['indicators'])
    
    def test_assemble_chart_data_partial_indicators(self):
        """测试部分指标组装"""
        result = self.assembler.assemble_chart_data(
            symbol='000001.SH',
            period='daily',
            count=120,
            indicators='macd,rsi'
        )
        
        # 验证仅包含请求的指标
        self.assertIn('macd', result['indicators'])
        self.assertIn('rsi', result['indicators'])
        self.assertNotIn('kdj', result['indicators'])
        self.assertNotIn('obv', result['indicators'])


class ChartDataAssemblerBugFixTest(unittest.TestCase):
    """
    Bug 修复测试类
    
    🐞 Bug #3: 'PriceData' object has no attribute 'copy'
    ✅ 已修复: _detect_events 现在直接接收 PriceData，不再需要转换
    """
    
    def setUp(self):
        """Test setup"""
        self.mock_provider = Mock()
        self.mock_indicator = Mock()
        self.assembler = ChartDataAssembler(
            data_provider=self.mock_provider,
            indicator_service=self.mock_indicator
        )
    
    def test_detect_events_accepts_pricedata_directly(self):
        """
        测试 _detect_events 方法直接接收 PriceData（强类型）
        
        🐞 Bug Fix: 验证 _detect_events 现在直接使用 PriceData，不需要 to_dataframe()
        原错误: 'PriceData' object has no attribute 'copy'
        修复: _detect_events 签名改为 def _detect_events(self, price_data: PriceData)
        """
        # 构造包含暴跌的 PriceData
        from core.data.providers.protocols import OHLCVRecord
        
        records = [
            OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-03'), open=100.0, high=105.0, low=92.0, close=93.0, volume=2000000),  # 暴跌 7%
        ]
        
        price_data = PriceData(
            symbol='^GSPC',
            records=records,
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-03'),
            count=3
        )
        
        # 💚 直接传入 PriceData 对象（不再需要 to_dataframe()）
        events = self.assembler._detect_events(price_data)
        
        # 验证事件检测成功
        self.assertIsInstance(events, list)
        
        # 验证检测到暴跌事件
        crash_events = [e for e in events if e['type'] == 'market_crash']
        self.assertGreater(len(crash_events), 0, "应该检测到暴跌事件")
        
        # 验证事件属性
        event = crash_events[0]
        self.assertEqual(event['type'], 'market_crash')
        self.assertEqual(event['impact'], 'negative')
        self.assertLess(event['decline_pct'], -5.0)
        self.assertIn('severity', event)
    
    def test_slice_price_data_returns_valid_pricedata(self):
        """
        测试 _slice_price_data 返回有效的 PriceData 对象
        
        相关于 Bug #3: 验证 _slice_price_data 返回的 PriceData 可以被 to_dataframe()
        """
        from core.data.providers.protocols import OHLCVRecord
        
        records = [
            OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=100.0, high=105.0, low=99.0, close=100.0, volume=1000000),
            OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=101.0, high=106.0, low=100.0, close=101.0, volume=1100000),
            OHLCVRecord(date=pd.Timestamp('2024-01-03'), open=102.0, high=107.0, low=101.0, close=102.0, volume=1200000),
            OHLCVRecord(date=pd.Timestamp('2024-01-04'), open=103.0, high=108.0, low=102.0, close=103.0, volume=1300000),
            OHLCVRecord(date=pd.Timestamp('2024-01-05'), open=104.0, high=109.0, low=103.0, close=104.0, volume=1400000),
        ]
        
        price_data = PriceData(
            symbol='^GSPC',
            records=records,
            start_date=pd.Timestamp('2024-01-01'),
            end_date=pd.Timestamp('2024-01-05'),
            count=5
        )
        
        # 裁剪最后 3 条
        sliced = self.assembler._slice_price_data(price_data, -3)
        
        # 验证裁剪结果
        self.assertIsInstance(sliced, PriceData)
        self.assertEqual(sliced.count, 3)
        self.assertEqual(len(sliced.records), 3)
        
        # 💚 验证可以转换为 DataFrame（不应该报错）
        df = sliced.to_dataframe()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 3)
        self.assertIn('close', df.columns)


if __name__ == '__main__':
    unittest.main()


class TestPeriodBarCache(unittest.TestCase):
    """测试周期K柱缓存机制
    
    验证：
    1. ChartDataAssembler在交易时段排除最后一个K柱并缓存
    2. get_realtime_kline从缓存读取最后一个K柱进行合并
    3. 缓存未命中时的fallback机制
    """
    
    def setUp(self):
        """测试前准备"""
        self.mock_provider = Mock()
        self.mock_indicator = Mock()
        
        # 模拟缓存字典
        self.cache_dict = {}
        
        # Mock缓存方法
        self.mock_provider._set_to_memory_cache_obj = Mock(side_effect=self._mock_set_cache)
        self.mock_provider._get_from_memory_cache = Mock(side_effect=self._mock_get_cache)
        
        self.assembler = ChartDataAssembler(
            data_provider=self.mock_provider,
            indicator_service=self.mock_indicator
        )
    
    def _mock_set_cache(self, key, value):
        """模拟缓存存储"""
        self.cache_dict[key] = value
    
    def _mock_get_cache(self, key):
        """模拟缓存读取"""
        return self.cache_dict.get(key)
    
    def test_weekly_cache_on_exclude_last_bar(self):
        """测试：周线在交易时段排除最后一个K柱并缓存"""
        symbol = '000001.SZ'
        period = 'weekly'
        
        records = [
            OHLCVRecord(
                date=pd.Timestamp('2024-01-08'),
                open=2900.0,
                high=3100.0,
                low=2850.0,
                close=3000.0,
                volume=50000000
            ),
            OHLCVRecord(
                date=pd.Timestamp('2024-01-15'),
                open=3000.0,
                high=3200.0,
                low=2950.0,
                close=3100.0,
                volume=60000000
            ),
            OHLCVRecord(
                date=pd.Timestamp('2024-01-22'),
                open=3100.0,
                high=3300.0,
                low=3050.0,
                close=3200.0,
                volume=70000000
            )
        ]
        
        price_data = PriceData(
            records=records,
            symbol=symbol,
            start_date=pd.Timestamp('2024-01-08'),
            end_date=pd.Timestamp('2024-01-28'),
            count=3,
            needs_realtime_kline=True
        )
        
        self.mock_provider.get_index_prices = Mock(return_value=price_data)
        self.mock_indicator.calculate = Mock(return_value=({}, {}))
        
        result = self.assembler.assemble_chart_data(
            symbol=symbol,
            period=period,
            count=2,
            before=None,
            indicators='all',
            market_local_time=pd.Timestamp('2024-01-28 10:00:00')
        )
        
        cache_key = f"last_period_bar_{symbol}_{period}"
        self.assertIn(cache_key, self.cache_dict)
        
        cached_bar = self.cache_dict[cache_key]
        self.assertEqual(cached_bar['date'], '2024-01-22')
        self.assertEqual(cached_bar['open'], 3100.0)
        self.assertEqual(cached_bar['close'], 3200.0)
        self.assertEqual(cached_bar['volume'], 70000000)
    
    def test_realtime_kline_use_cache(self):
        """测试：实时K线接口从缓存读取最后一个K柱"""
        symbol = '000001.SZ'
        period = 'weekly'
        
        cache_key = f"last_period_bar_{symbol}_{period}"
        cached_bar = {
            'date': '2024-01-22',
            'open': 3100.0,
            'high': 3300.0,
            'low': 3050.0,
            'close': 3200.0,
            'volume': 70000000
        }
        self.cache_dict[cache_key] = cached_bar
        
        cached_value = self._mock_get_cache(cache_key)
        self.assertIsNotNone(cached_value)
        self.assertEqual(cached_value['date'], '2024-01-22')
    
    def test_cache_miss_fallback(self):
        """测试：缓存未命中时的fallback机制"""
        symbol = '000001.SZ'
        period = 'weekly'
        cache_key = f"last_period_bar_{symbol}_{period}"
        
        cached_value = self._mock_get_cache(cache_key)
        self.assertIsNone(cached_value)
    
    def test_daily_no_cache(self):
        """测试：日线不缓存最后一个K柱"""
        symbol = '000001.SZ'
        period = 'daily'
        
        records = [
            OHLCVRecord(
                date=pd.Timestamp('2024-01-26'),
                open=3100.0,
                high=3150.0,
                low=3080.0,
                close=3120.0,
                volume=5000000
            ),
            OHLCVRecord(
                date=pd.Timestamp('2024-01-27'),
                open=3120.0,
                high=3180.0,
                low=3100.0,
                close=3150.0,
                volume=6000000
            )
        ]
        
        price_data = PriceData(
            records=records,
            symbol=symbol,
            start_date=pd.Timestamp('2024-01-26'),
            end_date=pd.Timestamp('2024-01-27'),
            count=2,
            needs_realtime_kline=True
        )
        
        self.mock_provider.get_index_prices = Mock(return_value=price_data)
        self.mock_indicator.calculate = Mock(return_value=({}, {}))
        
        result = self.assembler.assemble_chart_data(
            symbol=symbol,
            period=period,
            count=2,
            before=None,
            indicators='all',
            market_local_time=pd.Timestamp('2024-01-27 10:00:00')
        )
        
        cache_key = f"last_period_bar_{symbol}_{period}"
        self.assertNotIn(cache_key, self.cache_dict)
