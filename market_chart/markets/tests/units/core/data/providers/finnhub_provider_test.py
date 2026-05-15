"""
FinnhubDataProvider 单元测试

测试覆盖：
1. 初始化（有/无 API Key）
2. initialize 方法测试
3. API调用失败处理
4. 数据获取与标准化
5. test_provider 方法测试
"""

import pandas as pd
import unittest
from unittest.mock import patch, Mock


from core.data.providers.finnhub_provider import FinnhubDataProvider


class FinnhubProviderTest(unittest.TestCase):
    """FinnhubDataProvider 测试类"""
    
    def test_init_without_api_key(self):
        """测试无 API Key 初始化"""
        # 💚 不再使用 os.environ，直接 Mock 配置文件读取
        with patch.object(FinnhubDataProvider, '_load_api_key_from_config', return_value=None):
            provider = FinnhubDataProvider()
            
            self.assertIsNotNone(provider)
            # 新实现中没有 available 属性，通过 client 是否为 None 判断
            self.assertIsNone(provider.client)
    
    def test_init_with_api_key(self):
        """测试带 API Key 初始化（通过配置文件）"""
        test_api_key = "test_api_key_12345"
        
        # 💚 通过 Mock 配置文件返回 API Key
        with patch.object(FinnhubDataProvider, '_load_api_key_from_config', return_value=test_api_key):
            provider = FinnhubDataProvider()
            
            self.assertIsNotNone(provider)
            # 新实现中没有 api_key 属性，通过 client 是否存在判断初始化成功
            self.assertIsNotNone(provider.client)
    
    def test_initialize_method(self):
        """测试 initialize 方法"""
        # 💚 确保配置文件不提供 API Key
        with patch.object(FinnhubDataProvider, '_load_api_key_from_config', return_value=None):
            provider = FinnhubDataProvider()
            self.assertIsNone(provider.client)
            
            # 调用 initialize 方法初始化客户端
            provider.initialize(credential="test_credential_key")
            
            # 验证客户端已创建
            self.assertIsNotNone(provider.client)
    
    def test_initialize_without_credential(self):
        """测试 initialize 方法不提供凭证"""
        provider = FinnhubDataProvider()
        
        # 不提供凭证调用 initialize
        provider.initialize(credential="")
        
        # client 应该仍然是 None（如果初始化时就是 None）
        # 或者保持原样
    
    def test_get_test_symbol(self):
        """测试获取测试符号"""
        provider = FinnhubDataProvider()
        self.assertEqual(provider.get_test_symbol(), 'AAPL')
    
    def test_get_index_prices_unavailable(self):
        """测试在没有API Key时获取数据应失败"""
        # 💚 不再使用 os.environ
        with patch.object(FinnhubDataProvider, '_load_api_key_from_config', return_value=None):
            provider = FinnhubDataProvider()
            provider.client = None  # 确保 client 为 None
            
            with self.assertRaises(ValueError) as context:
                provider.get_index_prices('SPX', '2023-01-01', '2023-01-10', pd.Timestamp.now())
            
            self.assertIn('Finnhub API密钥未配置', str(context.exception))
    
    def test_get_index_prices_client_none_with_api_key(self):
        """测试 client=None 但调用API时应失败"""
        # 💚 通过配置文件提供 API Key
        with patch.object(FinnhubDataProvider, '_load_api_key_from_config', return_value="test_key"):
            provider = FinnhubDataProvider()
            provider.client = None  # 强制设置为 None
            
            with self.assertRaises(ValueError) as context:
                provider.get_index_prices('SPX', '2023-01-01', '2023-01-10', pd.Timestamp.now())
            
            self.assertIn('Finnhub API密钥未配置', str(context.exception))
    
    def test_provider_test_method(self):
        """测试 test_provider 类方法"""
        # Mock ConfigManager 返回包含 finnhub 配置
        with patch('core.data.providers.base_provider.ConfigManager') as MockConfigManager:
            mock_config_instance = MockConfigManager.return_value
            mock_data_config = Mock()
            mock_data_config.providers = [
                {
                    'id': 'finnhub',
                    'name': 'Finnhub',
                    'adapter_module': 'core.data.providers.finnhub_provider',
                    'adapter_class': 'FinnhubDataProvider'
                }
            ]
            mock_config_instance.get_provider_config.return_value = mock_data_config
            
            # 测试 test_provider（不会真正调用 API，因为没有真实凭证）
            result = FinnhubDataProvider.test_provider('finnhub', credential='test_credential')
            
            # 验证返回结构
            self.assertIn('status', result)
            self.assertIn('test_result', result)
            self.assertIn('available', result)
            self.assertIn('message', result)


if __name__ == '__main__':
    unittest.main()
