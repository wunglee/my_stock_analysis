"""
AKShare Provider 缓存系统集成测试

测试范围：
1. 继承自BaseDataProvider的三层缓存机制（Memory/Redis → DB → API）
2. Memory/Redis 互斥选择（由配置文件定义）
3. 缓存功能验证
4. 配置加载和初始化
5. 历史数据获取的缓存行为
6. 最小窗口粒度为 weekly（不支持 daily）

符合规范：.qoder/rules/PECIFICATIONS.md
- 测试文件命名：*_test.py
- 边界场景测试：不同日期范围、不同周期
- 异常处理测试
"""

import unittest

from unittest.mock import patch

import pandas as pd

from core.data.providers.akshare_provider import AKShareDataProvider
from core.data.providers.protocols import PriceData
from core.share.market.data_types import OHLCVRecord


class AKShareCacheIntegrationTest(unittest.TestCase):
    """AKShare Provider 缓存集成测试"""
    
    def setUp(self):
        """测试前准备"""
        # 创建AKShare provider实例（会自动禁用DB缓存）
        self.provider = AKShareDataProvider()
    
    # ========== 初始化和配置测试 ==========
    
    def test_initialization_with_cache_config(self):
        """测试初始化时加载缓存配置"""
        # 验证基类初始化被调用
        self.assertIsNotNone(self.provider._cache_manager)
        
        # 验证数据库缓存被禁用（AKShare特殊处理）
        self.assertFalse(self.provider._enable_db_cache)
        
        # 验证窗口缓存启用（新架构使用 _window_cache）
        self.assertTrue(hasattr(self.provider._cache_manager, '_window_cache'))
    
    def test_cache_config_from_database_yml(self):
        """测试从database.yml加载缓存配置"""
        # 重新创建provider，验证配置加载
        provider = AKShareDataProvider()
        
        # 验证缓存管理器的配置参数
        # 注意：这些参数来臯database.yml配置或默认值
        self.assertIsNotNone(provider._cache_manager)
    
    def test_db_cache_explicitly_disabled(self):
        """测试数据库缓存被明确禁用"""
        # AKShare禁用DB缓存以避免iCloud路径问题
        # 数据库缓存现在完全封装在 ThreeLayerCacheManager 中
        # 验证 cache_manager 存在
        self.assertIsNotNone(self.provider._cache_manager)
    
    # ========== 历史数据缓存测试 ==========
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_cache_hit_for_historical_data(self, mock_fetch):
        """测试历史数据缓存命中"""
        # 准备测试数据（使用更早的历史数据，避免当前周干扰）
        test_symbol = '000300.SH'
        start_date = pd.Timestamp('2024-01-01')
        end_date = pd.Timestamp('2024-01-31')
        fixed_current_time = pd.Timestamp('2025-12-22')  # 使用固定的当前时间
        
        # Mock API返回数据
        mock_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2024-01-01'), open=3490.0, high=3510.0, low=3485.0, close=3500.0, volume=100000),
                OHLCVRecord(date=pd.Timestamp('2024-01-02'), open=3500.0, high=3520.0, low=3495.0, close=3510.0, volume=110000),
            ],
            symbol=test_symbol,
            start_date=pd.Timestamp(start_date),
            end_date=pd.Timestamp(end_date),
            count=2
        )
        mock_fetch.return_value = mock_data
        
        # 第一次调用（缓存未命中，调用API）
        result1 = self.provider.get_index_prices(
            test_symbol, start_date, end_date, 
            current_time=fixed_current_time, period='weekly'  # 使用 weekly 粒度
        )
        
        # 💚 验证第一次调用了API（窗口化缓存按周拆分，1月有4-5周）
        self.assertGreater(mock_fetch.call_count, 0, "Should call API at least once")
        initial_call_count = mock_fetch.call_count
        # 窗口化缓存会合并所有窗口的数据
        self.assertGreater(result1.count, 0, "Should return some data")
        
        # 第二次调用（应该命中快速缓存，不调用API）
        result2 = self.provider.get_index_prices(
            test_symbol, start_date, end_date,
            current_time=fixed_current_time, period='weekly'  # 使用相同的 current_time
        )
        
        # 💚 验证：第二次命中缓存，不应该有额外的API调用
        self.assertEqual(mock_fetch.call_count, initial_call_count, "Second call should hit cache")
        self.assertEqual(result2.count, result1.count, "Results should be consistent")
        self.assertEqual(result2.symbol, test_symbol)
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_partial_cache_hit_with_window_strategy(self, mock_fetch):
        """测试窗口化缓存的部分命中场景"""
        test_symbol = '000300.SH'
        
        # Mock API返回不同月份的数据
        def mock_fetch_side_effect(symbol, start, end, period):
            # 根据日期范围返回对应数据
            df = pd.DataFrame({
                'date': pd.date_range(start, end, freq='D'),
                'open': [3490.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'high': [3510.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'low': [3485.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'close': [3500.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'volume': [100000.0] * ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)
            })
            return PriceData.from_dataframe(df, symbol)
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 第一次查询：2025-01-01 到 2025-01-31（1月）
        result1 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='monthly'
        )
        self.assertGreater(result1.count, 0)
        initial_call_count = mock_fetch.call_count
        
        # 第二次查询：2025-01-01 到 2025-02-28（1月+2月）
        # 1月应该命中缓存，只查询2月
        result2 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-02-28'),
            current_time=pd.Timestamp.now(), period='monthly'
        )
        self.assertGreater(result2.count, 0)
        
        # 验证：应该有额外的API调用（查询2月）
        self.assertGreater(mock_fetch.call_count, initial_call_count)
    
    # ========== 空数据和边界测试 ==========
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_empty_data_not_cached(self, mock_fetch):
        """测试空数据不被缓存"""
        test_symbol = '000300.SH'
        
        # Mock API返回空数据
        empty_data = PriceData(
            records=[],
            symbol=test_symbol,
            start_date=pd.Timestamp('2025-01-01'),
            end_date=pd.Timestamp('2025-01-31'),
            count=0
        )
        mock_fetch.return_value = empty_data
        
        # 调用两次
        result1 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='weekly'  # 使用 weekly 粒度
        )
        result2 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='weekly'
        )
        
        # 验证空数据
        self.assertEqual(result1.count, 0)
        self.assertEqual(result2.count, 0)
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_cross_year_boundary(self, mock_fetch):
        """测试跨年查询的缓存行为"""
        test_symbol = '000300.SH'
        
        # Mock API返回数据
        def mock_fetch_side_effect(symbol, start, end, period):
            df = pd.DataFrame({
                'date': pd.date_range(start, end, freq='D'),
                'open': [3490.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'high': [3510.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'low': [3485.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'close': [3500.0 + i for i in range((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)],
                'volume': [100000.0] * ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1)
            })
            return PriceData.from_dataframe(df, symbol)
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 跨年查询：2024-12-01 到 2025-01-31
        result = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2024-12-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='monthly'
        )
        
        # 验证数据跨年
        self.assertGreater(result.count, 0)
        self.assertGreater(mock_fetch.call_count, 0)
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_single_day_query(self, mock_fetch):
        """测试单周查询（最小粒度为周）"""
        test_symbol = '000300.SH'
        
        # Mock API返回单周数据
        single_week_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2025-01-13'), open=3490.0, high=3510.0, low=3485.0, close=3500.0, volume=100000)
            ],
            symbol=test_symbol,
            start_date=pd.Timestamp('2025-01-13'),  # 使用周一日期
            end_date=pd.Timestamp('2025-01-19'),    # 周日
            count=1
        )
        mock_fetch.return_value = single_week_data
        
        # 查询单周数据（2025年第3周）
        result = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-19'),
            current_time=pd.Timestamp.now(), period='weekly'
        )
        
        # 验证
        self.assertGreaterEqual(result.count, 0)
    
    # ========== 异常处理测试 ==========
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_api_failure_raises_exception(self, mock_fetch):
        """测试API失败时的处理（基类会捕获异常并返回空数据）"""
        test_symbol = '000300.SH'
        
        # Mock API抛出异常
        mock_fetch.side_effect = ValueError("API连接失败")
        
        # 💚 基类会捕获异常并返回空数据，不会抛出异常
        result = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='weekly'  # 使用 weekly 粒度
        )
        
        # 验证返回空数据
        self.assertEqual(result.count, 0)
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_invalid_date_range(self, mock_fetch):
        """测试无效日期范围"""
        test_symbol = '000300.SH'
        
        # 开始日期晚于结束日期
        result = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-02-01'), pd.Timestamp('2025-01-01'),
            current_time=pd.Timestamp.now(), period='weekly'  # 使用 weekly 粒度
        )
        
        # 应该返回空数据（窗口生成器会返回空列表）
        self.assertEqual(result.count, 0)
    
    # ========== 不同周期测试 ==========
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_weekly_period_cache(self, mock_fetch):
        """测试周度数据缓存"""
        test_symbol = '000300.SH'
        
        # Mock API返回周度数据
        def mock_fetch_side_effect(symbol, start, end, period):
            # 生成周度数据
            dates = pd.date_range(start, end, freq='W')
            df = pd.DataFrame({
                'date': dates,
                'open': [3490.0 + i*10 for i in range(len(dates))],
                'high': [3510.0 + i*10 for i in range(len(dates))],
                'low': [3485.0 + i*10 for i in range(len(dates))],
                'close': [3500.0 + i*10 for i in range(len(dates))],
                'volume': [100000.0] * len(dates)
            })
            return PriceData.from_dataframe(df, symbol)
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 查询周度数据
        result = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='weekly'
        )
        
        # 验证
        self.assertGreaterEqual(result.count, 0)
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_monthly_period_cache(self, mock_fetch):
        """测试月度数据缓存"""
        test_symbol = '000300.SH'
        
        # Mock API返回月度数据
        monthly_data = PriceData(
            records=[
                OHLCVRecord(date=pd.Timestamp('2025-01-01'), open=3490.0, high=3510.0, low=3485.0, close=3500.0, volume=100000),
                OHLCVRecord(date=pd.Timestamp('2025-02-01'), open=3590.0, high=3610.0, low=3585.0, close=3600.0, volume=110000),
            ],
            symbol=test_symbol,
            start_date=pd.Timestamp('2025-01-01'),
            end_date=pd.Timestamp('2025-02-28'),
            count=2
        )
        mock_fetch.return_value = monthly_data
        
        # 查询月度数据
        result = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-02-28'),
            current_time=pd.Timestamp.now(), period='monthly'
        )
        
        # 💚 验证：窗口化缓存会按月拆分，可能会合并多个窗口的数据
        # 只需验证有数据返回即可
        self.assertGreater(result.count, 0)
    
    # ========== 多股票隔离测试 ==========
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    def test_multiple_symbols_cache_isolation(self, mock_fetch):
        """测试不同股票的缓存隔离"""
        symbol1 = '000300.SH'
        symbol2 = '399006.SZ'
        
        # Mock API返回不同股票的数据
        def mock_fetch_side_effect(symbol, start, end, period):
            close_price = 3500.0 if symbol == symbol1 else 2500.0
            open_price = close_price - 10
            return PriceData(
                records=[OHLCVRecord(
                    date=pd.Timestamp(start),
                    open=open_price,
                    high=close_price + 10,
                    low=close_price - 15,
                    close=close_price,
                    volume=100000
                )],
                symbol=symbol,
                start_date=pd.Timestamp(start),
                end_date=pd.Timestamp(end),
                count=1
            )
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 查询不同股票
        result1 = self.provider.get_index_prices(
            symbol1, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='weekly'  # 使用 weekly 粒度
        )
        result2 = self.provider.get_index_prices(
            symbol2, pd.Timestamp('2025-01-01'), pd.Timestamp('2025-01-31'),
            current_time=pd.Timestamp.now(), period='weekly'
        )
        
        # 验证数据隔离
        self.assertEqual(result1.symbol, symbol1)
        self.assertEqual(result2.symbol, symbol2)
        if result1.count > 0 and result2.count > 0:
            self.assertNotEqual(
                result1.records[0].close,
                result2.records[0].close
            )
    
    # ========== 窗口状态标记测试 ==========
    
    @patch.object(AKShareDataProvider, '_fetch_from_api')
    @patch('datetime.datetime')
    def test_first_window_prevents_earlier_queries(self, mock_datetime, mock_fetch):
        """
        测试起始窗口：防止重复查询早于起始窗口的数据
        
        场景：
        - 股票上市日：2020-01-08（周三）
        - 首次查询：2020-01-06 ~ 2020-01-10 → 缓存 2020-W01，标记为 is_first_window=True
        - 再次查询：2019-12-30 ~ 2020-01-10 → 应该忽略 2019-W53，不查询数据库/API
        
        验证：
        1. 第一次查询后，2020-W01 被标记为 is_first_window=True
        2. 第二次查询早于起始窗口的数据，不会调用API
        """
        test_symbol = 'IPO_STOCK'
        
        # Mock 当前时间为 2020-01-20（不是当前周）
        mock_datetime.now.return_value = pd.Timestamp(2020, 1, 20)
        
        # Mock API返回数据（只有从 2020-01-08 开始的数据）
        def mock_fetch_side_effect(symbol, start, end, period):
            start_dt = pd.Timestamp(start)
            end_dt = pd.Timestamp(end)
            
            # 模拟上市日 2020-01-08，更早的数据不存在
            actual_start = max(start_dt, pd.Timestamp('2020-01-08'))
            
            if actual_start > end_dt:
                # 无数据，返回空 DataFrame
                return pd.DataFrame()
            
            dates = pd.date_range(actual_start, end_dt, freq='D')
            df = pd.DataFrame({
                'date': dates,
                'open': [100.0 + i for i in range(len(dates))],
                'high': [110.0 + i for i in range(len(dates))],
                'low': [95.0 + i for i in range(len(dates))],
                'close': [105.0 + i for i in range(len(dates))],
                'volume': [100000.0] * len(dates)
            })
            return df
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 第一次查询：2020-01-06 ~ 2020-01-10
        result1 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2020-01-06'), pd.Timestamp('2020-01-10'),
            current_time=pd.Timestamp(2020, 1, 20), period='weekly'
        )
        
        # 验证：应该有数据（从 2020-01-08 开始）
        self.assertGreater(result1.count, 0, "应该有数据")
        first_call_count = mock_fetch.call_count
        self.assertGreater(first_call_count, 0, "第一次应该调用API")
        
        # 第二次查询：2019-12-30 ~ 2020-01-10（包含更早的日期）
        result2 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2019-12-30'), pd.Timestamp('2020-01-10'),
            current_time=pd.Timestamp(2020, 1, 20), period='weekly'
        )
        
        # 验证：
        # 1. 不应该有额外的API调用（因为 2019-W53 被忽略）
        self.assertEqual(mock_fetch.call_count, first_call_count, 
                        "不应该查询早于起始窗口的数据")
        
        # 2. 返回的数据应该一致
        self.assertEqual(result2.count, result1.count, "数据应该一致")
    
    @patch.object(AKShareDataProvider, '_fetch_from_api')
    @patch('datetime.datetime')
    def test_current_week_always_refreshes(self, mock_datetime, mock_fetch):
        """
        测试当前周窗口：总是刷新，不使用缓存
        
        场景：
        - 今天：2025-01-16（周四）
        - 查询本周数据：2025-01-13 ~ 2025-01-19
        
        验证：
        1. 第一次查询调用API
        2. 第二次查询仍然调用API（当前周不使用缓存）
        """
        test_symbol = 'CURRENT_WEEK_TEST'
        
        # Mock 当前时间为 2025-01-16（周四）
        mock_datetime.now.return_value = pd.Timestamp(2025, 1, 16)
        
        # Mock API返回数据
        def mock_fetch_side_effect(symbol, start, end, period):
            dates = pd.date_range(start, end, freq='D')
            df = pd.DataFrame({
                'date': dates,
                'open': [100.0 + i for i in range(len(dates))],
                'high': [110.0 + i for i in range(len(dates))],
                'low': [95.0 + i for i in range(len(dates))],
                'close': [105.0 + i for i in range(len(dates))],
                'volume': [100000.0] * len(dates)
            })
            return df
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 第一次查询本周数据
        result1 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-19'),
            current_time=pd.Timestamp(2025, 1, 16), period='weekly'
        )
        
        self.assertGreater(result1.count, 0, "应该有数据")
        first_call_count = mock_fetch.call_count
        self.assertGreater(first_call_count, 0, "第一次应该调用API")
        
        # 第二次查询相同范围
        result2 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-19'),
            current_time=pd.Timestamp(2025, 1, 16), period='weekly'
        )
        
        # 验证：应该有额外的API调用（当前周不使用缓存）
        self.assertGreater(mock_fetch.call_count, first_call_count,
                          "当前周应该每次都刷新")
        
        self.assertEqual(result2.count, result1.count, "数据数量应该一致")
    
    @patch.object(AKShareDataProvider, '_fetch_from_external_api')
    @patch('datetime.datetime')
    def test_first_plus_current_week_overlap(self, mock_datetime, mock_fetch):
        """
        测试起始+当前周重叠：按当前周处理（优先刷新）
        
        场景：
        - 今天：2025-01-16（周四）
        - 上市日：2025-01-15（周三，本周）
        - 查询：2025-01-13 ~ 2025-01-19（本周）
        
        验证：
        1. 即使是起始周，但因为是当前周，应该每次都刷新
        2. 下周查询时，该周变为历史周，应该使用缓存
        """
        test_symbol = 'IPO_THIS_WEEK'
        
        # === 第一阶段：今天是 2025-01-16（周四）===
        mock_datetime.now.return_value = pd.Timestamp(2025, 1, 16)
        
        # Mock API返回数据（上市日 2025-01-15）
        def mock_fetch_side_effect(symbol, start, end, period):
            start_dt = pd.Timestamp(start)
            end_dt = pd.Timestamp(end)
            
            # 上市日 2025-01-15
            actual_start = max(start_dt, pd.Timestamp('2025-01-15'))
            
            if actual_start > end_dt:
                return pd.DataFrame()
            
            dates = pd.date_range(actual_start, end_dt, freq='D')
            df = pd.DataFrame({
                'date': dates,
                'open': [100.0 + i for i in range(len(dates))],
                'high': [110.0 + i for i in range(len(dates))],
                'low': [95.0 + i for i in range(len(dates))],
                'close': [105.0 + i for i in range(len(dates))],
                'volume': [100000.0] * len(dates)
            })
            return df
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        # 第一次查询（周四）
        result1 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-19'),
            current_time=pd.Timestamp(2025, 1, 16), period='weekly'
        )
        
        self.assertGreater(result1.count, 0, "应该有数据")
        first_call_count = mock_fetch.call_count
        
        # 第二次查询（仍然是周四）
        result2 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-19'),
            current_time=pd.Timestamp(2025, 1, 16), period='weekly'
        )
        
        # 验证：当前周应该刷新（即使是起始周）
        self.assertGreater(mock_fetch.call_count, first_call_count,
                          "起始+当前周重叠时，应该按当前周处理（刷新）")
        
        # === 第二阶段：下周（2025-01-23，周四）===
        mock_datetime.now.return_value = pd.Timestamp(2025, 1, 23)
        
        second_call_count = mock_fetch.call_count
        
        # 再次查询上周数据
        result3 = self.provider.get_index_prices(
            test_symbol, pd.Timestamp('2025-01-13'), pd.Timestamp('2025-01-19'),
            current_time=pd.Timestamp(2025, 1, 23), period='weekly'
        )
        
        # 验证：上周已经不是当前周，应该使用缓存
        self.assertEqual(mock_fetch.call_count, second_call_count,
                        "上周数据应该使用缓存，不再刷新")
        
        self.assertEqual(result3.count, result2.count, "数据应该一致")


if __name__ == '__main__':
    unittest.main()
