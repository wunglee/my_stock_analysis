"""
MemoryCache 单元测试

测试内存缓存层功能：
1. 基本读写操作
2. LRU 淘汰机制
3. TTL 过期机制
4. 边界场景（满缓存、空数据、过期数据等）
"""

import unittest
import time
import pandas as pd

from infrastructure.cache.memory import MemoryCache


class MemoryCacheTest(unittest.TestCase):
    """MemoryCache 功能测试"""
    
    def setUp(self):
        """测试初始化"""
        # 使用较小的缓存和短TTL便于测试
        self.cache = MemoryCache(max_windows=3, ttl=2)
    
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
        self.assertEqual(len(result['data']), 5)
        pd.testing.assert_frame_equal(result['data'], df)
    
    def test_get_non_existent(self):
        """测试读取不存在的缓存"""
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    def test_set_empty_dataframe(self):
        """空 DataFrame 无 known_empty 标记时被拒（防止误存未确认空数据）"""
        empty_df = pd.DataFrame()
        self.cache.set('399006.SZ', 'monthly', '2025-01', empty_df)

        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result,
                        "空 DF 无 known_empty 标记应被拒，调用方需显式声明意图")
    
    def test_set_none_data(self):
        """测试写入None"""
        self.cache.set('399006.SZ', 'monthly', '2025-01', None)
        
        # None不应被缓存
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    def test_multiple_symbols(self):
        """测试多个不同symbol的缓存"""
        df1 = self._create_test_df(3)
        df2 = self._create_test_df(4)
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df1)
        self.cache.set('000001.SZ', 'monthly', '2025-01', df2)
        
        result1 = self.cache.get('399006.SZ', 'monthly', '2025-01')
        result2 = self.cache.get('000001.SZ', 'monthly', '2025-01')
        
        self.assertEqual(len(result1['data']), 3)
        self.assertEqual(len(result2['data']), 4)
    
    def test_multiple_periods(self):
        """测试多个不同period的缓存"""
        df_monthly = self._create_test_df(3)
        df_daily = self._create_test_df(4)
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df_monthly)
        self.cache.set('399006.SZ', 'daily', '2025-01-01', df_daily)
        
        result_monthly = self.cache.get('399006.SZ', 'monthly', '2025-01')
        result_daily = self.cache.get('399006.SZ', 'daily', '2025-01-01')
        
        self.assertEqual(len(result_monthly['data']), 3)
        self.assertEqual(len(result_daily['data']), 4)
    
    # ========== LRU 淘汰机制测试 ==========
    
    def test_lru_eviction_when_full(self):
        """测试缓存满时的LRU淘汰"""
        df1 = self._create_test_df(1)
        df2 = self._create_test_df(2)
        df3 = self._create_test_df(3)
        df4 = self._create_test_df(4)
        
        # 填满缓存（max_windows=3）
        self.cache.set('399006.SZ', 'monthly', '2025-01', df1)
        self.cache.set('399006.SZ', 'monthly', '2025-02', df2)
        self.cache.set('399006.SZ', 'monthly', '2025-03', df3)
        
        # 再写入一个，应淘汰最老的（2025-01）
        self.cache.set('399006.SZ', 'monthly', '2025-04', df4)
        
        # 2025-01应被淘汰
        self.assertIsNone(self.cache.get('399006.SZ', 'monthly', '2025-01'))
        
        # 其他应存在
        self.assertIsNotNone(self.cache.get('399006.SZ', 'monthly', '2025-02'))
        self.assertIsNotNone(self.cache.get('399006.SZ', 'monthly', '2025-03'))
        self.assertIsNotNone(self.cache.get('399006.SZ', 'monthly', '2025-04'))
    
    def test_lru_update_on_access(self):
        """测试访问后LRU更新"""
        df1 = self._create_test_df(1)
        df2 = self._create_test_df(2)
        df3 = self._create_test_df(3)
        df4 = self._create_test_df(4)
        
        # 填满缓存
        self.cache.set('399006.SZ', 'monthly', '2025-01', df1)
        self.cache.set('399006.SZ', 'monthly', '2025-02', df2)
        self.cache.set('399006.SZ', 'monthly', '2025-03', df3)
        
        # 访问2025-01，使其成为最近使用
        self.cache.get('399006.SZ', 'monthly', '2025-01')
        
        # 再写入一个，应淘汰2025-02（现在是最老的）
        self.cache.set('399006.SZ', 'monthly', '2025-04', df4)
        
        # 2025-02应被淘汰
        self.assertIsNone(self.cache.get('399006.SZ', 'monthly', '2025-02'))
        
        # 2025-01因为被访问过，应该还在
        self.assertIsNotNone(self.cache.get('399006.SZ', 'monthly', '2025-01'))
    
    # ========== TTL 过期机制测试 ==========
    
    def test_ttl_expiration(self):
        """测试TTL过期"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        
        # 立即读取应成功
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNotNone(result)
        
        # 等待超过TTL（2秒）
        time.sleep(2.5)
        
        # 再次读取应返回None（已过期）
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
    
    def test_ttl_not_expired(self):
        """测试TTL未过期时仍可读取"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        
        # 等待一半TTL时间
        time.sleep(1)
        
        # 应仍可读取
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNotNone(result)
        self.assertEqual(len(result['data']), 5)
    
    def test_expired_entry_removed_on_access(self):
        """测试过期条目在访问时被移除"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        
        # 等待过期
        time.sleep(2.5)
        
        # 访问过期条目
        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)
        
        # 缓存统计应显示0个窗口（过期条目已被移除）
        stats = self.cache.get_stats()
        self.assertEqual(stats['total_windows'], 0)
    
    # ========== 缓存统计测试 ==========
    
    def test_get_stats_empty(self):
        """测试空缓存统计"""
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['total_windows'], 0)
        self.assertEqual(stats['max_windows'], 3)
        self.assertEqual(stats['usage_percent'], 0.0)
    
    def test_get_stats_partial(self):
        """测试部分填充缓存统计"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        self.cache.set('399006.SZ', 'monthly', '2025-02', df)
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['total_windows'], 2)
        self.assertEqual(stats['max_windows'], 3)
        self.assertAlmostEqual(stats['usage_percent'], 66.67, places=1)
    
    def test_get_stats_full(self):
        """测试满缓存统计"""
        df = self._create_test_df()
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        self.cache.set('399006.SZ', 'monthly', '2025-02', df)
        self.cache.set('399006.SZ', 'monthly', '2025-03', df)
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['total_windows'], 3)
        self.assertEqual(stats['max_windows'], 3)
        self.assertEqual(stats['usage_percent'], 100.0)
    
    # ========== 清空缓存测试 ==========
    
    def test_clear_cache(self):
        """测试清空缓存"""
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
        
        # 统计应为0
        stats = self.cache.get_stats()
        self.assertEqual(stats['total_windows'], 0)
    
    # ========== 数据隔离测试 ==========
    
    def test_data_independence(self):
        """测试缓存数据独立性（修改原数据不影响缓存）"""
        df = self._create_test_df()
        original_value = df.iloc[0]['close']
        
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)
        
        # 修改原DataFrame
        df.iloc[0, df.columns.get_loc('close')] = 999
        
        # 从缓存读取
        cached_result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        cached_df = cached_result['data']
        
        # 缓存中的数据应未被修改
        self.assertEqual(cached_df.iloc[0]['close'], original_value)
        self.assertNotEqual(cached_df.iloc[0]['close'], 999)
    
    # ========== 边界场景测试 ==========
    
    def test_large_dataframe(self):
        """测试大DataFrame缓存"""
        large_df = self._create_test_df(rows=10000)
        
        self.cache.set('399006.SZ', 'daily', '2025-01-01', large_df)
        result = self.cache.get('399006.SZ', 'daily', '2025-01-01')
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result['data']), 10000)
    
    def test_special_characters_in_symbol(self):
        """测试symbol中的特殊字符"""
        df = self._create_test_df()
        
        symbols = ['399006.SZ', '000001.SH', 'AAPL', 'BRK.B', 'SPX:INDEX']
        for symbol in symbols:
            self.cache.set(symbol, 'monthly', '2025-01', df)
            result = self.cache.get(symbol, 'monthly', '2025-01')
            self.assertIsNotNone(result, f"Failed for symbol: {symbol}")
    
    def test_window_key_edge_cases(self):
        """测试窗口键边界场景"""
        df = self._create_test_df()
        
        # 测试各种窗口键格式
        window_keys = [
            ('monthly', '2025-01'),
            ('monthly', '2024-12'),
            ('weekly', '2025-W01'),
            ('daily', '2025-01-01'),
            ('daily', '2025-12-31'),
            ('daily', '2024-02-29'),  # 闰年
        ]
        
        for period, window_key in window_keys:
            self.cache.set('399006.SZ', period, window_key, df)
            result = self.cache.get('399006.SZ', period, window_key)
            self.assertIsNotNone(result,
                f"Failed for period={period}, window_key={window_key}")

    # ========== known_empty 标记测试 ==========

    def test_known_empty_flag_stored_and_retrieved(self):
        """known_empty=True 无需 data，标记独立持久化"""
        self.cache.set('399006.SZ', 'monthly', '2025-01', known_empty=True)

        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNotNone(result)
        self.assertTrue(result['known_empty'])
        self.assertIsNone(result['data'])

    def test_known_empty_defaults_to_false(self):
        """不传 known_empty 时默认为 False"""
        df = self._create_test_df()
        self.cache.set('399006.SZ', 'monthly', '2025-01', df)

        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNotNone(result)
        self.assertFalse(result.get('known_empty', False))

    def test_known_empty_flag_with_non_empty_data(self):
        """known_empty=True 但 data 非空 — 标记应如实记录（调用方负责一致性）"""
        df = self._create_test_df(3)
        self.cache.set('399006.SZ', 'monthly', '2025-01', df, known_empty=True)

        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertTrue(result['known_empty'])
        self.assertEqual(len(result['data']), 3)

    def test_known_empty_does_not_affect_lru(self):
        """known_empty 窗口也参与 LRU 淘汰"""
        df1 = self._create_test_df(1)
        df3 = self._create_test_df(3)

        # 填满缓存（max_windows=3），前两个是已知空
        self.cache.set('399006.SZ', 'monthly', '2025-01', known_empty=True)
        self.cache.set('399006.SZ', 'monthly', '2025-02', known_empty=True)
        self.cache.set('399006.SZ', 'monthly', '2025-03', df3)

        # 再写入一个，应淘汰最老的（2025-01, known_empty）
        self.cache.set('399006.SZ', 'monthly', '2025-04', df1)

        self.assertIsNone(self.cache.get('399006.SZ', 'monthly', '2025-01'))
        self.assertIsNotNone(self.cache.get('399006.SZ', 'monthly', '2025-02'))

    def test_known_empty_expires_normally(self):
        """known_empty 窗口也遵循 TTL 过期"""
        self.cache.set('399006.SZ', 'monthly', '2025-01', known_empty=True)

        time.sleep(2.5)

        result = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNone(result)

    def test_known_empty_cache_hit_distinct_from_miss(self):
        """已知空（cache hit + known_empty=True）vs 未命中（None）— 调用方可区分"""
        self.cache.set('399006.SZ', 'monthly', '2025-01', known_empty=True)

        # 命中但已知空
        hit = self.cache.get('399006.SZ', 'monthly', '2025-01')
        self.assertIsNotNone(hit)
        self.assertTrue(hit['known_empty'])

        # 未命中
        miss = self.cache.get('399006.SZ', 'monthly', '2099-01')
        self.assertIsNone(miss)

    # ========== 空窗口缓存完整场景测试 ==========

    def test_empty_window_persistence_across_requests(self):
        """模拟两次请求：第一次标记空窗口，第二次应命中缓存而不触发重查"""

        # 第一次请求：标记窗口为空
        self.cache.set('600519.SH', 'weekly', '2025-W01', known_empty=True)
        self.cache.set('600519.SH', 'weekly', '2025-W02', self._create_test_df(5))
        self.cache.set('600519.SH', 'weekly', '2025-W03', known_empty=True)

        # 第二次请求：检查所有窗口
        cached_windows = {}
        missing_windows = []
        for wk in ['2025-W01', '2025-W02', '2025-W03']:
            result = self.cache.get('600519.SH', 'weekly', wk)
            if result is not None:
                cached_windows[wk] = {
                    'data': result['data'],
                    'known_empty': result.get('known_empty', False),
                }
            else:
                missing_windows.append(wk)

        # 所有窗口都应命中
        self.assertEqual(len(missing_windows), 0)
        self.assertEqual(len(cached_windows), 3)

        # W01 和 W03 应为已知空（data=None 而非空 DataFrame）
        self.assertTrue(cached_windows['2025-W01']['known_empty'])
        self.assertIsNone(cached_windows['2025-W01']['data'])
        self.assertFalse(cached_windows['2025-W02']['known_empty'])
        self.assertTrue(cached_windows['2025-W03']['known_empty'])

    def test_mixed_empty_and_data_windows_merge_safely(self):
        """空窗口应被跳过不参与合并（window_cache.py 消费者行为）"""
        df_normal = self._create_test_df(5)

        self.cache.set('399006.SZ', 'weekly', '2025-W01', known_empty=True)
        self.cache.set('399006.SZ', 'weekly', '2025-W02', df_normal)
        self.cache.set('399006.SZ', 'weekly', '2025-W03', df_normal)

        # 模拟 get_cached_and_missing_windows 的合并逻辑：跳过 known_empty
        cached_dfs = []
        for wk in ['2025-W01', '2025-W02', '2025-W03']:
            result = self.cache.get('399006.SZ', 'weekly', wk)
            if result is not None and not result.get('known_empty', False):
                cached_dfs.append(result['data'])

        merged = pd.concat(cached_dfs, ignore_index=True)

        # W01 被跳过（known_empty），W02+W03 贡献 10 行
        self.assertEqual(len(merged), 10)

    def test_all_windows_empty_scenario(self):
        """极端场景：所有窗口都是已知空，无数据可合并"""
        # 使用更大缓存（max_windows=5）避免 LRU 淘汰干扰测试
        big_cache = MemoryCache(max_windows=5, ttl=10)

        for i in range(5):
            big_cache.set('000001.SZ', 'weekly', f'2025-W{i+1:02d}', known_empty=True)

        # 所有窗口均为已知空，data 为 None
        for i in range(5):
            result = big_cache.get('000001.SZ', 'weekly', f'2025-W{i+1:02d}')
            self.assertIsNotNone(result)
            self.assertTrue(result['known_empty'])
            self.assertIsNone(result['data'])

        # 跳过 known_empty 后无可合并数据
        cached_dfs = []
        for i in range(5):
            result = big_cache.get('000001.SZ', 'weekly', f'2025-W{i+1:02d}')
            if result is not None and not result.get('known_empty', False):
                cached_dfs.append(result['data'])

        self.assertEqual(len(cached_dfs), 0)


if __name__ == '__main__':
    unittest.main()
