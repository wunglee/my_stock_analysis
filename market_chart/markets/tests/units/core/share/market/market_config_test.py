import unittest

from core.share.market.market_config import MarketConfig
from core.share.market.market_enums import MarketCode


class MarketConfigTest(unittest.TestCase):
    def setUp(self):
        self.manager = MarketConfig()

    def test_get_market_info_cn(self):
        info = self.manager.get_market_info(MarketCode.CN.value)
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get('currency'), 'CNY')
        self.assertIn('Asia/Shanghai', info.get('timezone', ''))

    def test_generate_config_template_and_validation(self):
        tpl = self.manager.generate_config_template(MarketCode.CN.value)
        self.assertEqual(tpl.get('market_type'), MarketCode.CN.value)
        self.assertIn(MarketCode.CN.value, tpl.get('market_configs', {}))
        self.assertIn('confidence_levels', tpl)
        # validate a correct-like config has no invalid market_type error
        errors = self.manager.validate_market_config({
            'market_type': MarketCode.CN.value,
            'market_configs': {MarketCode.CN.value: {}}
        })
        # may still have details missing, but invalid market_type should not be present
        self.assertTrue(all('不支持的市场类型' not in e for e in errors))

    def test_validate_invalid_market_type(self):
        errors = self.manager.validate_market_config({
            'market_type': 'XX',
            'market_configs': {}
        })
        self.assertTrue(any('不支持的市场类型' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
