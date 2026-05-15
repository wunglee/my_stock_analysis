"""
RedisCache 单元测试

测试Redis缓存层功能：
1. 基本读写操作（内存模拟模式）
2. 数据序列化和压缩
3. 边界场景测试
"""

import unittest
import pandas as pd

from infrastructure.cache.redis import RedisCache


class RedisCacheTest(unittest.TestCase):
    """RedisCache 功能测试"""
    
    def setUp(self):
        """测试初始化（使用内存模拟模式）"""
        self.cache = RedisCache(redis_client=None, ttl=3600, enable_compression=True)
    
    def _create_test_df(self, rows=5):
        """创建测试数据"""
        return pd.DataFrame({
            'date': pd.date_range('2025-01-01', periods=rows, freq='D'),
            'close': [100 + i for i in range(rows)],
            'volume': [1000 + i*100 for i in range(rows)]
        })
    
    # ========== 基本读写测试 ==========
    
    def test_set_and_get_success(self):
        """测试基本写入和读取"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        
        self.assertIsNotNone(result)
        # get()返回的是字典，包含'data'、'is_first_window'、'timestamp'
        self.assertIn('data', result)
        pd.testing.assert_frame_equal(result['data'], df)
    
    def test_get_non_existent(self):
        """测试读取不存在的缓存"""
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    def test_set_empty_dataframe(self):
        """测试写入空DataFrame"""
        empty_df = pd.DataFrame()
        self.cache.set('399006.SZ', 'monthly', '2025-01', empty_df)
        
        # 空DataFrame不应被缓存
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    def test_set_none_data(self):
        """测试写入None"""
        self.cache.set('399006.SZ', 'monthly', '2025-01', None)
        
        # None不应被缓存
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    # ========== 压缩功能测试 ==========
    
    def test_compression_enabled(self):
        """测试启用压缩"""
        cache_compressed = RedisCache(redis_client=None, enable_compression=True)
        df = self._create_test_df(rows=100)
        
        cache_compressed.set('399006.SZ', 'monthly', '2025-01', df)
        result = cache_compressed.get('399006.SZ', 'monthly', '2025-01')
        
        self.assertIsNotNone(result)
        pd.testing.assert_frame_equal(result['data'], df)
    
    def test_compression_disabled(self):
        """测试禁用压缩"""
        cache_uncompressed = RedisCache(redis_client=None, enable_compression=False)
        df = self._create_test_df(rows=100)
        
        cache_uncompressed.set('399006.SZ', 'monthly', '2025-01', df)
        result = cache_uncompressed.get('399006.SZ', 'monthly', '2025-01')
        
        self.assertIsNotNone(result)
        pd.testing.assert_frame_equal(result['data'], df)
    
    # ========== 数据完整性测试 ==========
    
    def test_data_types_preservation(self):
        """测试数据类型保持"""
        df = pd.DataFrame({
            'date': pd.date_range('2025-01-01', periods=3, freq='D'),
            'int_col': [1, 2, 3],
            'float_col': [1.1, 2.2, 3.3],
            'str_col': ['a', 'b', 'c'],
        })
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        
        result_df = result['data']
        self.assertEqual(result_df['int_col'].dtype, df['int_col'].dtype)
        self.assertEqual(result_df['float_col'].dtype, df['float_col'].dtype)
        self.assertEqual(result_df['str_col'].dtype, df['str_col'].dtype)
    
    def test_large_dataframe(self):
        """测试大DataFrame序列化"""
        large_df = self._create_test_df(rows=10000)
        
        self.cache.set('399006.SZ', 'daily', '2025-01-01', large_df)
        result = self.cache.get('399006.SZ', 'daily', '2025-01-01')
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result['data']), 10000)
        pd.testing.assert_frame_equal(result['data'], large_df)
    
    # ========== 键格式测试 ==========
    
    def test_cache_key_format(self):
        """测试缓存键格式"""
        df = self._create_test_df()
        
        # 写入数据
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        
        # 验证键格式：deepseekquant:window:symbol:period:window_key
        # 由于是内存模拟，直接检查内部存储
        expected_key = 'deepseekquant:window:399006.SZ:monthly:2025-01'
        self.assertIn(expected_key, self.cache._memory_store)
    
    def test_multiple_symbols_isolation(self):
        """测试多个symbol的数据隔离"""
        df1 = self._create_test_df(3)
        df2 = self._create_test_df(4)
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df1)
        self.cache.set('000001.SZ', 'monthly', '2025-01', df2)
        
        result1 = self.cache.get('399006.SZ', 'monthly', '2025-01')
        result2 = self.cache.get('000001.SZ', 'monthly', '2025-01')
        
        self.assertEqual(len(result1['data']), 3)
        self.assertEqual(len(result2['data']), 4)
    
    # ========== 清空缓存测试 ==========
    
    def test_clear_cache(self):
        """测试清空缓存（仅内存模拟模式）"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        self.cache.set('399006.SZ', 'monthly', '2025-02', df)
        
        # 清空前应有数据
        self.assertIsNotNone(self.cache.get('399006.SZ', 'monthly', '2025-01'))
        
        # 清空
        self.cache.clear()
        
        # 清空后应无数据
        self.assertIsNone(self.cache.get('399006.SZ', 'monthly', '2025-01'))
        self.assertIsNone(self.cache.get('399006.SZ', 'monthly', '2025-02'))
    
    # ========== 异常处理测试 ==========
    
    def test_corrupted_data_handling(self):
        """测试损坏数据的处理"""
        # 手动插入无效数据到内部存储
        cache_key = 'deepseekquant:window:399006.SZ:monthly:2025-01'
        self.cache._memory_store[cache_key] = b'invalid_pickle_data'
        
        # 读取应返回None而不是抛出异常
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    def test_special_characters_in_key(self):
        """测试键中的特殊字符"""
        df = self._create_test_df()
        
        test_cases = [
            ('SPX:INDEX', 'daily', '2025-01-01'),
            ('BRK.B', 'monthly', '2025-01'),
            ('A股指数', 'weekly', '2025-W01'),
        ]
        
        for symbol, period, window_key in test_cases:
            self.cache.set(symbol, period, window_key, df)
            result = self.cache.get(symbol, period, window_key)
            self.assertIsNotNone(result, 
                f"Failed for symbol={symbol}, period={period}, window_key={window_key}")


if __name__ == '__main__':
    unittest.main()
