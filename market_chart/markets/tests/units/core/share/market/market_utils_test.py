"""
测试 MarketUtils 工具类

职责：
- 测试市场识别和推断功能
- 测试数据格式标准化功能
- 不包含时间相关功能的测试（已迁移到 MarketTimeUtils）
"""

import unittest

import pandas as pd

from core.share.market.market_utils import MarketUtils


class TestMarketUtils(unittest.TestCase):
    """测试 MarketUtils 工具类"""

    def test_is_index(self):
        """测试证券类型判断"""
        # 测试上海指数
        self.assertTrue(MarketUtils.is_index('000001.SH'))  # 上证指数
        self.assertTrue(MarketUtils.is_index('000300.SH'))  # 沪深300
        
        # 测试深圳指数
        self.assertTrue(MarketUtils.is_index('399001.SZ'))  # 深证成指
        self.assertTrue(MarketUtils.is_index('399006.SZ'))  # 创业板指
        
        # 测试个股
        self.assertFalse(MarketUtils.is_index('600000.SH'))  # 浦发银行
        self.assertFalse(MarketUtils.is_index('000001.SZ'))  # 平安银行
        self.assertFalse(MarketUtils.is_index('300001.SZ'))  # 特锐德
        
        # 测试美股和其它
        self.assertFalse(MarketUtils.is_index('^GSPC'))  # 标普500（美股）
        self.assertFalse(MarketUtils.is_index('AAPL'))    # 苹果（美股）
        
        # 测试边界情况
        self.assertFalse(MarketUtils.is_index(''))
        self.assertFalse(MarketUtils.is_index(None))
    
    def test_standardize_format_valid_data(self):
        """测试有效数据标准化"""
        # 创建测试数据（A股格式）
        df = pd.DataFrame({
            'date': ['2023-01-03', '2023-01-02', '2023-01-01'],  # 乱序
            'open': [100.0, 99.0, 98.0],
            'high': [102.0, 101.0, 100.0],
            'low': [98.0, 97.0, 96.0],
            'close': [101.0, 100.0, 99.0],
            'volume': [1000, 1100, 1200]
        })
        
        result = MarketUtils.standardize_format(df)
        
        # 验证数据已排序（按时间升序）
        self.assertEqual(len(result), 3)
        self.assertEqual(result.iloc[0]['close'], 99.0)  # 2023-01-01
        self.assertEqual(result.iloc[1]['close'], 100.0)  # 2023-01-02
        self.assertEqual(result.iloc[2]['close'], 101.0)  # 2023-01-03
        
        # 验证列名标准化
        expected_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        self.assertListEqual(list(result.columns), expected_columns)
    
    def test_standardize_format_chinese_columns(self):
        """测试中文列名数据标准化"""
        # 创建测试数据（港股/美股格式）
        df = pd.DataFrame({
            '日期': ['2023-01-03', '2023-01-02', '2023-01-01'],
            '开盘': [100.0, 99.0, 98.0],
            '最高': [102.0, 101.0, 100.0],
            '最低': [98.0, 97.0, 96.0],
            '收盘': [101.0, 100.0, 99.0],
            '成交量': [1000, 1100, 1200]
        })
        
        result = MarketUtils.standardize_format(df)
        
        # 验证数据已排序（按时间升序）
        self.assertEqual(len(result), 3)
        self.assertEqual(result.iloc[0]['close'], 99.0)  # 2023-01-01
        self.assertEqual(result.iloc[1]['close'], 100.0)  # 2023-01-02
        self.assertEqual(result.iloc[2]['close'], 101.0)  # 2023-01-03
        
        # 验证列名标准化
        expected_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        self.assertListEqual(list(result.columns), expected_columns)
    
    def test_standardize_format_missing_columns(self):
        """测试缺少列的数据标准化"""
        # 创建测试数据（缺少open/high/low列）
        df = pd.DataFrame({
            'date': ['2023-01-01', '2023-01-02', '2023-01-03'],
            'close': [99.0, 100.0, 101.0],
            'volume': [1000, 1100, 1200]
        })
        
        result = MarketUtils.standardize_format(df)
        
        # 验证缺失列使用close填充
        self.assertEqual(result.iloc[0]['open'], 99.0)
        self.assertEqual(result.iloc[0]['high'], 99.0)
        self.assertEqual(result.iloc[0]['low'], 99.0)
        
        # 验证列名标准化
        expected_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        self.assertListEqual(list(result.columns), expected_columns)

    def test_standardize_format_missing_date_close_columns(self):
        """测试缺少日期或收盘价列的数据标准化"""
        # 创建测试数据（缺少date列）
        df = pd.DataFrame({
            'open': [100.0, 99.0, 98.0],
            'high': [102.0, 101.0, 100.0],
            'low': [98.0, 97.0, 96.0],
            'close': [101.0, 100.0, 99.0],
            'volume': [1000, 1100, 1200]
        })
        
        # 应该抛出ValueError
        with self.assertRaises(ValueError) as context:
            MarketUtils.standardize_format(df)
        
        self.assertIn("Cannot find date or close columns", str(context.exception))
    
    def test_standardize_format_to_price_data_valid_data(self):
        """测试有效数据标准化为PriceData"""
        # 创建测试数据（A股格式）
        df = pd.DataFrame({
            'date': ['2023-01-03', '2023-01-02', '2023-01-01'],  # 乱序
            'open': [100.0, 99.0, 98.0],
            'high': [102.0, 101.0, 100.0],
            'low': [98.0, 97.0, 96.0],
            'close': [101.0, 100.0, 99.0],
            'volume': [1000, 1100, 1200]
        })
        
        result = MarketUtils.standardize_format_to_price_data(df, "TEST")
        
        # 验证返回类型
        from core.data.providers.protocols import PriceData
        self.assertIsInstance(result, PriceData)
        
        # 验证数据已排序（按时间升序）
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.records[0].close, 99.0)  # 2023-01-01
        self.assertEqual(result.records[1].close, 100.0)  # 2023-01-02
        self.assertEqual(result.records[2].close, 101.0)  # 2023-01-03
        
        # 验证元数据
        self.assertEqual(result.symbol, "TEST")
        self.assertEqual(result.count, 3)
    
    def test_standardize_format_to_price_data_multiindex_columns(self):
        """测试MultiIndex列名数据标准化为PriceData"""
        # 创建测试数据（Yahoo Finance格式）
        columns = pd.MultiIndex.from_tuples([
            ('Open', 'AAPL'), ('High', 'AAPL'), ('Low', 'AAPL'), 
            ('Close', 'AAPL'), ('Volume', 'AAPL')
        ])
        df = pd.DataFrame([
            [100.0, 105.0, 99.0, 104.0, 1000],
            [101.0, 106.0, 100.0, 105.0, 1100]
        ], columns=columns, index=pd.date_range('2023-01-01', periods=2))
        
        result = MarketUtils.standardize_format_to_price_data(df, "AAPL")
        
        # 验证返回类型
        from core.data.providers.protocols import PriceData
        self.assertIsInstance(result, PriceData)
        
        # 验证数据
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0].close, 104.0)
        self.assertEqual(result.records[1].close, 105.0)
        
        # 验证元数据
        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.count, 2)
    
    def test_standardize_format_to_price_data_empty_data(self):
        """测试空数据标准化为PriceData"""
        # 创建空的DataFrame
        df = pd.DataFrame()
        
        result = MarketUtils.standardize_format_to_price_data(df, "EMPTY")
        
        # 验证返回类型
        from core.data.providers.protocols import PriceData
        self.assertIsInstance(result, PriceData)
        
        # 验证空数据
        self.assertEqual(len(result.records), 0)
        self.assertEqual(result.symbol, "EMPTY")
        self.assertEqual(result.count, 0)

    def test_standardize_format_with_symbol_parameter(self):
        """测试standardize_format方法的symbol参数"""
        # 创建测试数据（Yahoo Finance格式）
        columns = pd.MultiIndex.from_tuples([
            ('Open', 'AAPL'), ('High', 'AAPL'), ('Low', 'AAPL'), 
            ('Close', 'AAPL'), ('Volume', 'AAPL')
        ])
        df = pd.DataFrame([
            [100.0, 105.0, 99.0, 104.0, 1000],
            [101.0, 106.0, 100.0, 105.0, 1100]
        ], columns=columns, index=pd.date_range('2023-01-01', periods=2))
        
        result = MarketUtils.standardize_format(df, "AAPL")
        
        # 验证数据
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]['close'], 104.0)
        self.assertEqual(result.iloc[1]['close'], 105.0)
        
        # 验证列名标准化
        expected_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        self.assertListEqual(list(result.columns), expected_columns)


if __name__ == '__main__':
    unittest.main()
