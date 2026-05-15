"""
数据库缓存层（DBCache）单元测试

测试范围：
1. 基本功能测试（读取、写入）
2. 边界场景测试（空数据、None数据）
3. 异常处理测试（数据库服务不可用、读写失败）
4. 数据隔离测试（不同股票代码）
"""

import unittest
from unittest.mock import Mock

import pandas as pd

from infrastructure.cache.db import DBCache


class DBCacheTest(unittest.TestCase):
    """DBCache 单元测试"""
    
    def setUp(self):
        """每个测试前的准备工作"""
        # Mock 数据库服务
        self.mock_db_service = Mock()
        self.cache = DBCache(db_service=self.mock_db_service)
    
    # ========== 基本功能测试 ==========
    
    def test_get_success(self):
        """测试成功从数据库读取"""
        # 准备测试数据
        df = pd.DataFrame({
            'date': pd.date_range('2025-01-01', periods=10),
            'close': [100 + i for i in range(10)]
        })
        self.mock_db_service.get_cached_data.return_value = df
        
        # 调用
        result = self.cache.get('399006.SZ', '2025-01-01', '2025-01-10')
        
        # 验证
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 10)
        self.mock_db_service.get_cached_data.assert_called_once_with(
            '399006.SZ', '2025-01-01', '2025-01-10'
        )
    
    def test_get_returns_none(self):
        """测试数据库返回 None"""
        self.mock_db_service.get_cached_data.return_value = None
        
        result = self.cache.get('399006.SZ', '2025-01-01', '2025-01-10')
        
        self.assertIsNone(result)
    
    def test_get_returns_empty_dataframe(self):
        """测试数据库返回空 DataFrame"""
        self.mock_db_service.get_cached_data.return_value = pd.DataFrame()
        
        result = self.cache.get('399006.SZ', '2025-01-01', '2025-01-10')
        
        self.assertIsNone(result)
    
    def test_set_success(self):
        """测试成功写入数据库"""
        df = pd.DataFrame({
            'date': pd.date_range('2025-01-01', periods=10),
            'close': [100 + i for i in range(10)]
        })
        
        # 调用
        self.cache.set('399006.SZ', df)
        
        # 验证
        self.mock_db_service.cache_data.assert_called_once_with('399006.SZ', df)
    
    def test_set_empty_dataframe(self):
        """测试写入空 DataFrame（应该跳过）"""
        df = pd.DataFrame()
        
        self.cache.set('399006.SZ', df)
        
        # 应该不调用数据库服务
        self.mock_db_service.cache_data.assert_not_called()
    
    def test_set_none_data(self):
        """测试写入 None（应该跳过）"""
        self.cache.set('399006.SZ', None)
        
        # 应该不调用数据库服务
        self.mock_db_service.cache_data.assert_not_called()
    
    # ========== 异常处理测试 ==========
    
    def test_get_with_no_db_service(self):
        """测试没有数据库服务时的读取"""
        cache = DBCache(db_service=None)
        
        result = cache.get('399006.SZ', '2025-01-01', '2025-01-10')
        
        self.assertIsNone(result)
    
    def test_set_with_no_db_service(self):
        """测试没有数据库服务时的写入"""
        cache = DBCache(db_service=None)
        df = pd.DataFrame({'close': [100, 101]})
        
        # 应该不抛出异常
        cache.set('399006.SZ', df)
    
    def test_get_raises_exception(self):
        """测试数据库读取抛出异常"""
        self.mock_db_service.get_cached_data.side_effect = Exception("DB connection error")
        
        result = self.cache.get('399006.SZ', '2025-01-01', '2025-01-10')
        
        # 应该返回 None 而不是抛出异常
        self.assertIsNone(result)
    
    def test_set_raises_exception(self):
        """测试数据库写入抛出异常"""
        self.mock_db_service.cache_data.side_effect = Exception("DB connection error")
        df = pd.DataFrame({'close': [100, 101]})
        
        # 应该不抛出异常
        try:
            self.cache.set('399006.SZ', df)
        except Exception:
            self.fail("set() 不应该抛出异常")
    
    # ========== 数据隔离测试 ==========
    
    def test_multiple_symbols_isolation(self):
        """测试不同股票代码的数据隔离"""
        df1 = pd.DataFrame({'close': [100, 101]})
        df2 = pd.DataFrame({'close': [200, 201]})
        
        # 配置 mock 返回
        def mock_get(symbol, start, end):
            if symbol == '399006.SZ':
                return df1
            elif symbol == '000001.SZ':
                return df2
            return None
        
        self.mock_db_service.get_cached_data.side_effect = mock_get
        
        # 读取不同股票
        result1 = self.cache.get('399006.SZ', '2025-01-01', '2025-01-10')
        result2 = self.cache.get('000001.SZ', '2025-01-01', '2025-01-10')
        
        # 验证数据不同
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)
        self.assertEqual(result1['close'].iloc[0], 100)
        self.assertEqual(result2['close'].iloc[0], 200)
    
    # ========== 日期范围测试 ==========
    
    def test_get_with_different_date_ranges(self):
        """测试不同日期范围的查询"""
        df1 = pd.DataFrame({
            'date': pd.date_range('2025-01-01', periods=31),
            'close': [100 + i for i in range(31)]
        })
        df2 = pd.DataFrame({
            'date': pd.date_range('2025-02-01', periods=28),
            'close': [200 + i for i in range(28)]
        })
        
        # 配置 mock
        def mock_get(symbol, start, end):
            if start.startswith('2025-01'):
                return df1
            elif start.startswith('2025-02'):
                return df2
            return None
        
        self.mock_db_service.get_cached_data.side_effect = mock_get
        
        # 查询不同月份
        result1 = self.cache.get('399006.SZ', '2025-01-01', '2025-01-31')
        result2 = self.cache.get('399006.SZ', '2025-02-01', '2025-02-28')
        
        # 验证
        self.assertEqual(len(result1), 31)
        self.assertEqual(len(result2), 28)
        self.assertEqual(result1['close'].iloc[0], 100)
        self.assertEqual(result2['close'].iloc[0], 200)


if __name__ == '__main__':
    unittest.main()
