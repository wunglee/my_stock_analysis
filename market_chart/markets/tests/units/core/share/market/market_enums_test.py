import unittest

from core.share.market.market_enums import MarketCode, DataSource


class MarketEnumsTest(unittest.TestCase):
    def test_market_code_values_and_validation(self):
        """测试市场代码枚举的值和验证功能"""
        codes = MarketCode.get_all_codes()
        self.assertIn('CN', codes)
        self.assertIn('US', codes)
        self.assertIn('HK', codes)
        self.assertTrue(MarketCode.is_valid('CN'))
        self.assertFalse(MarketCode.is_valid('XX'))
        # __str__ should return value
        self.assertEqual(str(MarketCode.CN), 'CN')

    def test_data_source_values_and_validation(self):
        """测试数据源枚举的值和验证功能"""
        sources = DataSource.get_all_sources()
        self.assertIn('yahoo', sources)
        self.assertIn('mock', sources)
        self.assertTrue(DataSource.is_valid('yahoo'))
        self.assertFalse(DataSource.is_valid('unknown_source'))
        self.assertEqual(str(DataSource.MOCK), 'mock')

    def test_market_code_parse(self):
        """测试市场代码解析功能（字符串/枚举 -> 枚举）"""
        # 测试字符串解析
        self.assertEqual(MarketCode.parse('CN'), MarketCode.CN)
        self.assertEqual(MarketCode.parse('us'), MarketCode.US)  # 小写自动转大写
        self.assertEqual(MarketCode.parse('Hk'), MarketCode.HK)  # 混合大小写
        
        # 测试枚举解析（直接返回）
        self.assertEqual(MarketCode.parse(MarketCode.US), MarketCode.US)
        
        # 测试无效值回退到 UNKNOWN
        self.assertEqual(MarketCode.parse('invalid'), MarketCode.UNKNOWN)
        self.assertEqual(MarketCode.parse(None), MarketCode.UNKNOWN)
        self.assertEqual(MarketCode.parse(123), MarketCode.UNKNOWN)


if __name__ == '__main__':
    unittest.main()
