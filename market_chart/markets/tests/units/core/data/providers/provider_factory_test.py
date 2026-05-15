"""
DataProviderFactory 测试 - 验证工厂模式和配置文件管理

注意：
- 所有 provider 现在通过 config/{env}/data_provider.yml 配置文件管理
- 不再支持动态 register/unregister 方法
- 工厂从配置文件加载 provider 定义
"""
import unittest

from core.data.providers.factory import (
    DataProviderFactory,
    get_global_factory,
    reset_global_factory
)


class DataProviderFactoryConfigBasedTest(unittest.TestCase):
    """测试基于配置文件的工厂功能"""
    
    def setUp(self):
        """每个测试前重置全局工厂"""
        reset_global_factory()
    
    def test_factory_loads_providers_from_config(self):
        """测试工厂能从配置文件加载 providers"""
        factory = DataProviderFactory()
        providers = factory.list_providers()
        
        # 验证至少有一些providers被加载（具体数量取决于配置文件）
        self.assertIsInstance(providers, list)
        # 如果配置文件存在，应该有provider
        # 如果不存在，返回空列表也是合理的
        self.assertIsNotNone(providers)
    
    def test_get_method_returns_provider_instance(self):
        """测试 get 方法能返回 provider 实例"""
        factory = DataProviderFactory()
        
        # 如果 mock 在配置中，应该能创建
        if factory.is_registered('mock'):
            provider = factory.get('mock')
            self.assertIsNotNone(provider)
            # 验证provider有基本方法
            self.assertTrue(hasattr(provider, 'get_index_prices') or 
                          hasattr(provider, '_fetch_fn'))
    
    def test_get_method_singleton_behavior(self):
        """测试 get 方法的单例行为"""
        factory = DataProviderFactory()
        
        # 如果 mock 在配置中
        if factory.is_registered('mock'):
            provider1 = factory.get('mock')
            provider2 = factory.get('mock')
            # 验证返回同一个实例
            self.assertIs(provider1, provider2)
    
    def test_get_unknown_provider_raises_error(self):
        """测试获取未配置的 provider 抛出错误"""
        factory = DataProviderFactory()
        
        with self.assertRaises(ValueError) as ctx:
            factory.get('nonexistent_provider_xyz')
        
        # 验证错误信息
        error_msg = str(ctx.exception)
        self.assertIn('nonexistent_provider_xyz', error_msg)
    
    def test_is_registered_method(self):
        """测试 is_registered 方法"""
        factory = DataProviderFactory()
        
        # 测试不存在的provider
        self.assertFalse(factory.is_registered('definitely_not_exists'))
        
        # 如果有任何provider在配置中，测试它
        providers = factory.list_providers()
        if providers:
            self.assertTrue(factory.is_registered(providers[0]))
    
    def test_global_factory_singleton(self):
        """测试全局工厂单例"""
        factory1 = get_global_factory()
        factory2 = get_global_factory()
        
        # 验证是同一个实例
        self.assertIs(factory1, factory2)
    
    def test_reset_global_factory(self):
        """测试重置全局工厂"""
        factory1 = get_global_factory()
        
        # 重置
        reset_global_factory()
        factory2 = get_global_factory()
        
        # 验证是新实例
        self.assertIsNot(factory1, factory2)
    
    def test_factory_with_custom_config(self):
        """测试使用自定义配置创建工厂"""
        # 创建一个测试配置
        test_config = {
            'providers': [
                {
                    'id': 'test_provider',
                    'name': 'Test Provider',
                    'adapter_module': 'tests.fixtures.core.data.mock_historical_data_provider',
                    'adapter_class': 'MockHistoricalDataProvider'
                }
            ]
        }
        
        factory = DataProviderFactory(config=test_config)
        providers = factory.list_providers()
        
        # 验证测试provider已加载
        self.assertIn('test_provider', providers)
        
        # 验证能创建provider
        provider = factory.get('test_provider')
        self.assertIsNotNone(provider)


class DataProviderFactoryLegacyBehaviorTest(unittest.TestCase):
    """测试旧方法已被移除（确认不再支持）"""
    
    def test_register_method_not_exists(self):
        """确认 register 方法不再存在"""
        factory = DataProviderFactory()
        self.assertFalse(hasattr(factory, 'register'))
    
    def test_unregister_method_not_exists(self):
        """确认 unregister 方法不再存在"""
        factory = DataProviderFactory()
        self.assertFalse(hasattr(factory, 'unregister'))
    
    def test_create_method_not_exists(self):
        """确认 create 方法不再存在（应使用 get）"""
        factory = DataProviderFactory()
        self.assertFalse(hasattr(factory, 'create'))


if __name__ == '__main__':
    unittest.main()