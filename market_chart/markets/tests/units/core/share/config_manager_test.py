""" 
配置管理器测试
"""

import json
import os
import tempfile
import unittest

from core.share.config_manager import (
    ConfigManager, MonitoringConfig, AlertingConfig, ProvidersConfig, SystemConfig, MarketConfig
)


class TestConfigManager(unittest.TestCase):
    """测试配置管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        self.config_file = self.temp_file.name
        self.temp_file.close()
    
    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        # 重置 ConfigManager 单例，避免测试间干扰
        ConfigManager._instance = None
        ConfigManager._initialized = False
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        manager = ConfigManager()
        self.assertIsNotNone(manager._config)
    
    def test_get_monitoring_config(self):
        """测试获取监控配置"""
        manager = ConfigManager()
        config = manager.get_monitoring_config()
        self.assertIsInstance(config, MonitoringConfig)
        self.assertEqual(config.check_interval, 300)
    
    def test_get_alerting_config(self):
        """测试获取告警配置"""
        manager = ConfigManager()
        config = manager.get_alerting_config()
        self.assertIsInstance(config, AlertingConfig)
    
    def test_get_data_config(self):
        """测试获取数据配置"""
        # 默认环境是dev，使用dev/data.yml中的配置
        manager = ConfigManager()
        config = manager.get_provider_config()
        self.assertIsInstance(config, ProvidersConfig)

    def test_get_market_config(self):
        """测试获取数据配置"""
        # 默认环境是dev，使用dev/data.yml中的配置
        manager = ConfigManager()
        config = manager.get_market_config()
        self.assertIsInstance(config, MarketConfig)
        # dev环境使用 market_sources 映射，不再有 primary_source
        self.assertIsNotNone(config.market_sources)
        # 验证 CN 市场使用 akshare
        self.assertEqual(config.market_sources.get('CN'), 'akshare')
    def test_get_system_config(self):
        """测试获取系统配置"""
        manager = ConfigManager()
        config = manager.get_system_config()
        self.assertIsInstance(config, SystemConfig)
    
    def test_get_nested_key(self):
        """测试获取嵌套键"""
        manager = ConfigManager()
        value = manager.get('monitoring.check_interval', 100)
        self.assertEqual(value, 300)
    
    def test_set_nested_key(self):
        """测试设置嵌套键"""
        manager = ConfigManager()
        manager.set('monitoring.check_interval', 600)
        value = manager.get('monitoring.check_interval')
        self.assertEqual(value, 600)
    
    def test_save_config(self):
        """测试保存配置"""
        manager = ConfigManager()
        manager.set('test_key', 'test_value')
        
        with open(self.config_file, 'r') as f:
            saved_config = json.load(f)
        
        self.assertEqual(saved_config['test_key'], 'test_value')
    
    def test_load_config(self):
        """测试加载配置"""
        # 重置单例以确保使用 test 环境
        ConfigManager._instance = None
        # 在测试环境中，我们不测试JSON文件加载，因为YAML配置优先级更高
        # 我们测试get方法的基本功能
        manager = ConfigManager(environment='test')
        # 测试从YAML配置中获取值（test/data_provider.yml 中 default_index 为 SPX）
        value = manager.get('data_provider.default_index')
        self.assertEqual(value, 'SPX')
    
    def test_yaml_config_loading(self):
        """测试YAML配置加载"""
        # 使用开发环境配置
        manager = ConfigManager(environment='dev')
        # market_sources 现在从 market.yml 读取
        market_sources = manager.get('markets.market_sources')
        self.assertIsNotNone(market_sources)
        # 验证 CN 和 US 市场配置存在
        self.assertIn('CN', market_sources)
        self.assertIn('US', market_sources)
    
    def test_environment_encapsulation(self):
        """测试环境封装（外部不应直接获取环境）"""
        # 重置单例以确保测试独立
        ConfigManager._instance = None
        
        # 外部不应直接获取环境，应通过 ConfigManager 实例获取配置
        manager = ConfigManager(environment='dev')
        
        # 验证可以获取配置（环境已被封装）
        data_config = manager.get('data_provider')
        self.assertIsNotNone(data_config)
        
        # 验证 _get_environment() 是私有方法
        self.assertTrue(hasattr(ConfigManager, '_get_environment'))

        # 重置单例以切换环境
        ConfigManager._instance = None
        test_manager = ConfigManager(environment='test')
        test_value = test_manager.get('data_provider.default_index')
        self.assertEqual(test_value, 'SPX')

    def test_get_credential_with_nested_key(self):
        """测试获取嵌套的 credential 值"""
        manager = ConfigManager()
        # 假设配置中有 akshare.ut
        value = manager.get_credential('akshare.ut')
        # 验证返回的是字符串（ut token 格式）
        if value is not None:
            self.assertIsInstance(value, str)
            self.assertEqual(len(value), 32)  # ut token 应为 32 位

    def test_get_credential_with_flat_key(self):
        """测试获取扁平的 credential 值"""
        manager = ConfigManager()
        # 获取 mock_provider
        value = manager.get_credential('mock_provider')
        self.assertIsNotNone(value)
        self.assertIsInstance(value, str)

    def test_get_credential_with_default_value(self):
        """测试获取不存在的 credential 值时使用默认值"""
        manager = ConfigManager()
        default_value = 'default_credential'
        value = manager.get_credential('nonexistent.key', default_value)
        self.assertEqual(value, default_value)

    def test_get_credential_with_none_default(self):
        """测试获取不存在的 credential 值时默认返回 None"""
        manager = ConfigManager()
        value = manager.get_credential('nonexistent.key')
        self.assertIsNone(value)

    def test_set_credential_with_nested_key(self):
        """测试设置嵌套的 credential 值"""
        manager = ConfigManager()
        test_value = 'test_ut_7eea3edcaed734bea9cbfc24409ed989'

        result = manager.set_credential('akshare.ut', test_value)

        self.assertTrue(result)
        # 验证设置成功
        value = manager.get_credential('akshare.ut')
        self.assertEqual(value, test_value)

    def test_set_credential_with_flat_key(self):
        """测试设置扁平的 credential 值"""
        manager = ConfigManager()
        test_value = 'test_credential'

        result = manager.set_credential('mock_provider', test_value)

        self.assertTrue(result)
        # 验证设置成功
        value = manager.get_credential('mock_provider')
        self.assertEqual(value, test_value)

    def test_set_credential_create_nested_structure(self):
        """测试设置 credential 时自动创建嵌套结构"""
        manager = ConfigManager()
        test_value = 'nested_value'

        # 设置一个多层的嵌套键
        result = manager.set_credential('level1.level2.level3', test_value)

        self.assertTrue(result)
        # 验证嵌套结构创建成功
        value = manager.get_credential('level1.level2.level3')
        self.assertEqual(value, test_value)

    def test_set_credential_overwrite_existing(self):
        """测试设置 credential 覆盖已存在的值"""
        manager = ConfigManager()
        original_value = 'original_ut_7eea3edcaed734bea9cbfc24409ed989'
        new_value = 'new_ut_7eea3edcaed734bea9cbfc24409ed989'

        # 先设置原始值
        manager.set_credential('akshare.ut', original_value)
        # 验证设置成功
        self.assertEqual(manager.get_credential('akshare.ut'), original_value)

        # 覆盖为新值
        result = manager.set_credential('akshare.ut', new_value)

        self.assertTrue(result)
        # 验证覆盖成功
        value = manager.get_credential('akshare.ut')
        self.assertEqual(value, new_value)
        self.assertNotEqual(value, original_value)

    def test_get_credential_after_set_credential(self):
        """测试 set_credential 后能通过 get_credential 获取到值"""
        manager = ConfigManager()
        test_key = 'test.credential.key'
        test_value = 'test_credential_value'

        # 设置值
        set_result = manager.set_credential(test_key, test_value)
        self.assertTrue(set_result)

        # 获取值
        get_result = manager.get_credential(test_key)

        self.assertEqual(get_result, test_value)

    def test_get_credential_deeply_nested(self):
        """测试获取多层嵌套的 credential 值（5层嵌套）"""
        manager = ConfigManager()
        # 设置5层嵌套的值
        nested_key = 'level1.level2.level3.level4.level5'
        test_value = 'deeply_nested_value'
        manager.set_credential(nested_key, test_value)

        # 获取多层嵌套的值
        result = manager.get_credential(nested_key)

        self.assertEqual(result, test_value)

    def test_set_credential_deeply_nested(self):
        """测试设置多层嵌套的 credential 值"""
        manager = ConfigManager()
        # 设置5层嵌套的值
        nested_key = 'a.b.c.d.e'
        test_value = '5_level_nested_value'

        result = manager.set_credential(nested_key, test_value)

        self.assertTrue(result)
        # 验证每一层都存在
        self.assertIsNotNone(manager.get_credential('a'))
        self.assertIsNotNone(manager.get_credential('a.b'))
        self.assertIsNotNone(manager.get_credential('a.b.c'))
        self.assertIsNotNone(manager.get_credential('a.b.c.d'))
        self.assertEqual(manager.get_credential('a.b.c.d.e'), test_value)

    def test_get_credential_consistency_with_set_credential(self):
        """测试 get_credential 和 set_credential 对多层嵌套 key 的处理一致性"""
        manager = ConfigManager()
        test_cases = [
            'single_key',
            'two.level',
            'three.level.deep',
            'four.level.deep.nested',
            'five.level.deep.nested.structure'
        ]

        for i, key in enumerate(test_cases):
            test_value = f'test_value_{i}'
            # 设置值
            set_result = manager.set_credential(key, test_value)
            self.assertTrue(set_result, f"set_credential failed for key: {key}")

            # 获取值并验证一致性
            get_result = manager.get_credential(key)
            self.assertEqual(get_result, test_value, f"get_credential returned different value for key: {key}")

if __name__ == '__main__':
    unittest.main()

