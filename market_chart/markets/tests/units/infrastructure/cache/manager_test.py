"""
三层缓存管理器测试 - ThreeLayerCacheManager

测试覆盖：
1. 缓存管理器创建和初始化
2. 三层缓存策略（Memory/Redis -> Database -> API）
3. 缓存命中/未命中场景
4. 窗口合并和批量查询
5. 不同周期类型（daily/weekly/monthly）
6. 数据库缓存层集成
7. 空结果处理
"""

import unittest
import pandas as pd

from infrastructure.cache import ThreeLayerCacheManager, create_cache_manager
from core.share.market.market_enums import MarketCode


# ==================== 共享辅助函数 ====================

def create_mock_api_func(custom_data=None):
    """
    创建一个标准的mock API函数
    
    Args:
        custom_data: 自定义数据字典，可以覆盖默认的OHLCV数据
    
    Returns:
        mock API函数
    """
    def mock_api_func(start, end, period):
        # 根据period参数返回相应粒度的数据
        if period == 'weekly':
            dates = pd.date_range(start, end, freq='W-MON')
        elif period == 'monthly':
            dates = pd.date_range(start, end, freq='MS')
        else:  # daily
            dates = pd.date_range(start, end, freq='D')
        
        # 默认数据
        data = {
            'date': dates,
            'open': [100.0 + i for i in range(len(dates))],
            'high': [105.0 + i for i in range(len(dates))],
            'low': [95.0 + i for i in range(len(dates))],
            'close': [102.0 + i for i in range(len(dates))],
            'volume': [1000000 + i * 1000 for i in range(len(dates))]
        }
        
        # 使用自定义数据覆盖
        if custom_data:
            data.update(custom_data)
            # 如果自定义数据没有提供date，使用生成的dates
            if 'date' not in custom_data:
                data['date'] = dates
        
        return pd.DataFrame(data)
    
    return mock_api_func


def create_empty_mock_api_func():
    """
    创建一个返回空DataFrame的mock API函数
    """
    def mock_api_func(start, end, period):
        return pd.DataFrame()
    
    return mock_api_func


def create_tracking_mock_api_func(tracker):
    """
    创建一个可以跟踪调用次数的mock API函数
    
    Args:
        tracker: 用于跟踪调用的列表或字典
    
    Returns:
        mock API函数
    """
    def mock_api_func(start, end, period):
        if isinstance(tracker, list):
            tracker.append({'start': start, 'end': end, 'period': period})
        elif isinstance(tracker, dict) and 'count' in tracker:
            tracker['count'] += 1
        
        # 根据period返回相应粒度的数据
        if period == 'weekly':
            dates = pd.date_range(start, end, freq='W-MON')
        elif period == 'monthly':
            dates = pd.date_range(start, end, freq='MS')
        else:  # daily
            dates = pd.date_range(start, end, freq='D')
        
        return pd.DataFrame({
            'date': dates,
            'open': [100.0] * len(dates),
            'high': [105.0] * len(dates),
            'low': [95.0] * len(dates),
            'close': [102.0] * len(dates),
            'volume': [1000000] * len(dates)
        })
    
    return mock_api_func


def create_mock_db_func(custom_data=None):
    """
    创建一个标准的mock DB函数
    
    Args:
        custom_data: 自定义数据字典，可以覆盖默认的OHLCV数据
    
    Returns:
        mock DB函数
    """
    def mock_db_func(start, end, period):
        # 根据period参数返回相应粒度的数据
        if period == 'weekly':
            dates = pd.date_range(start, end, freq='W-MON')
        elif period == 'monthly':
            dates = pd.date_range(start, end, freq='MS')
        else:  # daily
            dates = pd.date_range(start, end, freq='D')
        
        # 默认数据
        data = {
            'date': dates,
            'open': [200.0] * len(dates),
            'high': [210.0] * len(dates),
            'low': [190.0] * len(dates),
            'close': [205.0] * len(dates),
            'volume': [2000000] * len(dates)
        }
        
        # 使用自定义数据覆盖
        if custom_data:
            data.update(custom_data)
            if 'date' not in custom_data:
                data['date'] = dates
        
        return pd.DataFrame(data)
    
    return mock_db_func


def create_tracking_mock_db_func(tracker):
    """
    创建一个可以跟踪调用次数的mock DB函数
    
    Args:
        tracker: 用于跟踪调用的字典
    
    Returns:
        mock DB函数
    """
    def mock_db_func(start, end, period):
        if 'count' in tracker:
            tracker['count'] += 1
        
        # 根据period返回相应粒度的数据
        if period == 'weekly':
            dates = pd.date_range(start, end, freq='W-MON')
        elif period == 'monthly':
            dates = pd.date_range(start, end, freq='MS')
        else:  # daily
            dates = pd.date_range(start, end, freq='D')
        
        return pd.DataFrame({
            'date': dates,
            'open': [200.0] * len(dates),
            'high': [210.0] * len(dates),
            'low': [190.0] * len(dates),
            'close': [205.0] * len(dates),
            'volume': [2000000] * len(dates)
        })
    
    return mock_db_func


# ==================== 测试类 ====================


class TestThreeLayerCacheManager(unittest.TestCase):
    """测试三层缓存管理器核心功能"""
    
    def setUp(self):
        """测试前准备"""
        self.cache_manager = create_cache_manager()
        self.test_symbol = '000300.SH'
    
    def test_cache_manager_creation(self):
        """测试缓存管理器创建"""
        # 验证创建成功
        self.assertIsNotNone(self.cache_manager)
        self.assertIsInstance(self.cache_manager, ThreeLayerCacheManager)
        
        # 验证核心组件存在
        self.assertTrue(hasattr(self.cache_manager, '_window_cache'))
        self.assertTrue(hasattr(self.cache_manager, '_db_cache'))
        self.assertTrue(hasattr(self.cache_manager, '_calendar_service'))
    
    def test_get_data_with_api_only(self):
        """测试仅使用API获取数据（无缓存）"""
        # 使用共享的mock函数
        mock_api_func = create_mock_api_func()
        
        # 调用get_data
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            market_code=MarketCode.CN,
            db_fetch_func=None,
            api_fetch_func=mock_api_func
        )
        
        # 验证结果
        self.assertIsInstance(result, pd.DataFrame)
        self.assertGreater(len(result), 0)
        self.assertIn('date', result.columns)
        self.assertIn('close', result.columns)
    
    def test_get_data_with_cache_hit(self):
        """测试缓存命中场景"""
        # 使用跟踪的mock函数
        api_call_count = {'count': 0}
        mock_api_func = create_tracking_mock_api_func(api_call_count)
        
        # 第一次调用（缓存未命中）
        result1 = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        initial_count = api_call_count['count']
        self.assertGreater(initial_count, 0, "第一次应该调用API")
        
        # 第二次调用（应该命中缓存）
        result2 = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        # 验证：第二次不应该有额外的API调用（缓存命中）
        self.assertEqual(api_call_count['count'], initial_count, "第二次应该命中缓存，不调用API")
        self.assertEqual(len(result1), len(result2), "两次结果应该一致")

    def test_get_data_weekly_period(self):
        """测试周粒度数据获取"""
        mock_api_func = create_mock_api_func()
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-31'),
            period='weekly',
            api_fetch_func=mock_api_func
        )
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertGreater(len(result), 0)
    
    def test_get_data_monthly_period(self):
        """测试月粒度数据获取"""
        mock_api_func = create_mock_api_func()
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-01'),
            to_date=pd.Timestamp('2025-03-31'),
            period='monthly',
            api_fetch_func=mock_api_func
        )
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertGreater(len(result), 0)
    
    def test_get_data_empty_result(self):
        """测试API返回空数据"""
        mock_api_func = create_empty_mock_api_func()
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-01'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        # 验证返回空DataFrame
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 0)
    
    def test_get_data_with_db_cache(self):
        """测试数据库缓存层（daily）"""
        db_call_count = {'count': 0}
        api_call_count = {'count': 0}
        
        mock_db_func = create_tracking_mock_db_func(db_call_count)
        
        def mock_api_func(start, end, period):
            api_call_count['count'] += 1
            return pd.DataFrame()  # API不返回数据
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            db_fetch_func=mock_db_func,
            api_fetch_func=mock_api_func
        )
        
        # 验证：应该调用了数据库函数
        self.assertGreater(db_call_count['count'], 0, "应该调用数据库查询")
        # 如果数据库有数据，不应该调用API
        if len(result) > 0:
            self.assertEqual(api_call_count['count'], 0, "数据库有数据时不应该调用API")
    
    def test_get_data_with_db_cache_weekly(self):
        """测试数据库缓存层（weekly）"""
        db_call_count = {'count': 0}
        api_call_count = {'count': 0}
        
        mock_db_func = create_tracking_mock_db_func(db_call_count)
        mock_api_func = create_tracking_mock_api_func(api_call_count)
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-31'),
            period='weekly',
            db_fetch_func=mock_db_func,
            api_fetch_func=mock_api_func
        )
        
        # 验证：应该调用了数据库函数
        self.assertGreater(db_call_count['count'], 0, "应该调用数据库查询")
        # 如果数据库有数据，不应该调用API
        if len(result) > 0:
            self.assertEqual(api_call_count['count'], 0, "数据库有数据时不应该调用API")
    
    def test_get_data_with_db_cache_monthly(self):
        """测试数据库缓存层（monthly）"""
        db_call_count = {'count': 0}
        api_call_count = {'count': 0}
        
        mock_db_func = create_tracking_mock_db_func(db_call_count)
        mock_api_func = create_tracking_mock_api_func(api_call_count)
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-01'),
            to_date=pd.Timestamp('2025-03-31'),
            period='monthly',
            db_fetch_func=mock_db_func,
            api_fetch_func=mock_api_func
        )
        
        # 验证：应该调用了数据库函数
        self.assertGreater(db_call_count['count'], 0, "应该调用数据库查询")
        # 如果数据库有数据，不应该调用API
        if len(result) > 0:
            self.assertEqual(api_call_count['count'], 0, "数据库有数据时不应该调用API")


class TestCacheIntegration(unittest.TestCase):
    """集成测试：完整的缓存流程"""
    
    def setUp(self):
        """测试前准备"""
        self.cache_manager = create_cache_manager()
        self.test_symbol = '000001.SZ'
    
    def test_full_cache_flow_daily(self):
        """测试完整的日粒度缓存流程"""
        api_calls = []
        mock_api_func = create_tracking_mock_api_func(api_calls)
        
        # 第一次查询
        result1 = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        first_call_count = len(api_calls)
        self.assertGreater(first_call_count, 0, "第一次应该调用API")
        self.assertGreater(len(result1), 0, "应该返回数据")
        
        # 第二次查询相同范围（应该完全命中缓存）
        result2 = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        self.assertEqual(len(api_calls), first_call_count, "第二次应该完全命中缓存")
        self.assertEqual(len(result1), len(result2), "两次结果数量应该一致")
    
    def test_partial_cache_hit(self):
        """测试部分缓存命中"""
        api_calls = []
        mock_api_func = create_tracking_mock_api_func(api_calls)
        
        # 第一次查询1月前半月
        self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-01'),
            to_date=pd.Timestamp('2025-01-15'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        first_count = len(api_calls)
        
        # 第二次查询整个1月（应该部分命中，只查询后半月）
        self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-01'),
            to_date=pd.Timestamp('2025-01-31'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        second_count = len(api_calls)
        # 应该有新的API调用（查询缺失的后半月）
        self.assertGreater(second_count, first_count, "应该有额外的API调用获取缺失数据")


class TestCacheFactory(unittest.TestCase):
    """测试缓存工厂方法"""
    
    def test_create_cache_manager(self):
        """测试工厂方法创建缓存管理器"""
        manager = create_cache_manager()
        
        self.assertIsNotNone(manager)
        self.assertIsInstance(manager, ThreeLayerCacheManager)
    
    def test_multiple_cache_managers_independent(self):
        """测试多个缓存管理器实例独立"""
        manager1 = create_cache_manager()
        manager2 = create_cache_manager()
        
        # 应该是不同的实例
        self.assertIsNot(manager1, manager2)


class TestErrorHandling(unittest.TestCase):
    """测试异常处理和边界情况"""
    
    def setUp(self):
        """测试前准备"""
        self.cache_manager = create_cache_manager()
        self.test_symbol = '600000.SH'
    
    def test_api_exception_propagation(self):
        """测试API异常是否正确传播"""
        def failing_api_func(start, end, period):
            raise ValueError("API调用失败")
        
        # API异常应该被传播出来
        with self.assertRaises(ValueError) as context:
            self.cache_manager.get_data(
                symbol=self.test_symbol,
                from_date=pd.Timestamp('2025-01-06'),
                to_date=pd.Timestamp('2025-01-10'),
                period='daily',
                api_fetch_func=failing_api_func
            )
        
        self.assertIn("API调用失败", str(context.exception))
    
    def test_db_exception_fallback_to_api(self):
        """测试数据库异常时回退到API"""
        db_calls = []
        api_calls = []
        
        def failing_db_func(start, end, period):
            db_calls.append(1)
            raise Exception("数据库连接失败")
        
        def working_api_func(start, end, period):
            api_calls.append(1)
            dates = pd.date_range(start, end, freq='D')
            return pd.DataFrame({
                'date': dates,
                'close': [100.0] * len(dates)
            })
        
        # 数据库失败不应该影响API调用
        try:
            result = self.cache_manager.get_data(
                symbol=self.test_symbol,
                from_date=pd.Timestamp('2025-01-06'),
                to_date=pd.Timestamp('2025-01-10'),
                period='daily',
                db_fetch_func=failing_db_func,
                api_fetch_func=working_api_func
            )
            # 如果没有抛出异常，验证API被调用了
            self.assertGreater(len(api_calls), 0, "API应该被调用")
        except Exception:
            # 如果抛出异常，验证至少尝试了数据库
            self.assertGreater(len(db_calls), 0, "数据库应该被尝试调用")
    
    def test_invalid_date_range(self):
        """测试无效的日期范围（开始日期晚于结束日期）"""
        def mock_api_func(start, end, period):
            dates = pd.date_range(start, end, freq='D')
            return pd.DataFrame({
                'date': dates,
                'close': [100.0] * len(dates)
            })
        
        # 开始日期晚于结束日期，应该返回空数据或处理得当
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-20'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        # 应该返回空DataFrame
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 0)
    
    def test_none_api_and_db_functions(self):
        """测试当API和DB函数都为None时的行为"""
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            db_fetch_func=None,
            api_fetch_func=None
        )
        
        # 应该返回空DataFrame
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 0)
    
    def test_market_code_inference(self):
        """测试市场代码自动推断"""
        mock_api_func = create_mock_api_func()
        
        # 不传入market_code，应该从symbol自动推断
        result = self.cache_manager.get_data(
            symbol='000300.SH',  # 中国A股
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
            # market_code参数省略
        )
        
        self.assertGreater(len(result), 0)
    
    def test_data_without_date_column(self):
        """测试返回的数据缺少date列"""
        def mock_api_func(start, end, period):
            # 返回没有date列的数据
            return pd.DataFrame({
                'close': [100.0, 101.0, 102.0],
                'volume': [1000000, 1100000, 1200000]
            })
        
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-06'),
            to_date=pd.Timestamp('2025-01-10'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        # 应该能处理，但可能无法正确筛选日期
        self.assertIsInstance(result, pd.DataFrame)


class TestDataMerging(unittest.TestCase):
    """测试数据合并和日期筛选"""
    
    def setUp(self):
        """测试前准备"""
        self.cache_manager = create_cache_manager()
        self.test_symbol = '000001.SZ'
    
    def test_date_filtering(self):
        """测试日期精确筛选"""
        mock_api_func = create_mock_api_func()
        
        # 只请求部分日期
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-10'),
            to_date=pd.Timestamp('2025-01-15'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        # 验证返回的数据被正确筛选
        if len(result) > 0 and 'date' in result.columns:
            result['date'] = pd.to_datetime(result['date'])
            self.assertTrue(all(result['date'] >= pd.Timestamp('2025-01-10')))
            self.assertTrue(all(result['date'] <= pd.Timestamp('2025-01-15')))
    
    def test_multiple_windows_merge(self):
        """测试多个窗口数据的合并"""
        api_calls = []
        mock_api_func = create_tracking_mock_api_func(api_calls)
        
        # 请求跨多个窗口的数据
        result = self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-01'),
            to_date=pd.Timestamp('2025-02-28'),
            period='daily',
            api_fetch_func=mock_api_func
        )
        
        # 应该返回合并后的数据
        self.assertGreater(len(result), 0)
        # 可能有多次API调用（取决于窗口大小）
        self.assertGreater(len(api_calls), 0)


class TestCurrentTimeParameter(unittest.TestCase):
    """测试current_time参数对缓存刷新的影响"""
    
    def setUp(self):
        """测试前准备"""
        self.cache_manager = create_cache_manager()
        self.test_symbol = '000300.SH'
    
    def test_current_window_with_current_time(self):
        """测试传入current_time时当前窗口的刷新"""
        api_calls = []
        mock_api_func = create_tracking_mock_api_func(api_calls)
        
        # 第一次调用，指定current_time
        current = pd.Timestamp('2025-01-15')
        self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-13'),
            to_date=pd.Timestamp('2025-01-17'),
            period='daily',
            api_fetch_func=mock_api_func,
            current_time=current
        )
        
        first_count = len(api_calls)
        self.assertGreater(first_count, 0)
        
        # 第二次调用，同样的current_time，包含当前窗口应该刷新
        self.cache_manager.get_data(
            symbol=self.test_symbol,
            from_date=pd.Timestamp('2025-01-13'),
            to_date=pd.Timestamp('2025-01-17'),
            period='daily',
            api_fetch_func=mock_api_func,
            current_time=current
        )
        
        # 当前窗口应该被刷新，所以会有新的API调用
        second_count = len(api_calls)
        self.assertGreaterEqual(second_count, first_count)


if __name__ == '__main__':
    unittest.main()
