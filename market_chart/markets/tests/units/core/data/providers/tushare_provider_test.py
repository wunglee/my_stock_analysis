"""
TushareDataProvider 单元测试

基于重写后的 tushare_provider.py
测试重点：
1. 初始化行为（从环境变量或配置文件获取token）
2. API可用性检查
3. 数据获取功能（指数、个股）
4. 数据标准化
5. 错误处理
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock, Mock
import pandas as pd


# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../../..'))

from core.data.providers.tushare_provider import TushareDataProvider
from core.data.providers.protocols import PriceData
from core.share.market.data_types import OHLCVRecord


class TushareProviderInitializationTest(unittest.TestCase):
    """测试 TushareDataProvider 初始化"""
    
    @patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config')
    def test_init_without_token(self, mock_load_token):
        """测试无 Token 初始化 - API 不可用"""
        # 💚 不再使用 os.environ，直接 Mock 配置文件读取
        mock_load_token.return_value = None
        
        provider = TushareDataProvider()
        
        # 验证实例创建成功
        self.assertIsNotNone(provider)
        # 验证 API 不可用
        self.assertFalse(provider.available)
        # 验证 ts_pro 为 None
        self.assertIsNone(provider.ts_pro)
    
    # 💚 已删除以下测试（不再支持环境变量）：
    # - test_init_with_env_token
    # - test_env_token_priority_over_config
    
    @patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config')
    @patch('tushare.pro_api')
    @patch('tushare.set_token')
    def test_init_with_config_token(self, mock_set_token, mock_pro_api, mock_load_token):
        """测试从配置文件获取 Token（💚 唯一来源）"""
        mock_load_token.return_value = "config_token_67890"
        mock_ts_pro = MagicMock()
        mock_pro_api.return_value = mock_ts_pro
        mock_ts_pro.trade_cal.return_value = pd.DataFrame()
        
        provider = TushareDataProvider()
        
        # 验证使用配置文件中的token
        mock_set_token.assert_called_once_with("config_token_67890")
        self.assertTrue(provider.available)


class TushareProviderAPITest(unittest.TestCase):
    """测试 TushareDataProvider API 功能"""
    
    def test_get_test_symbol(self):
        """测试获取测试符号"""
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value=None):
            provider = TushareDataProvider()
            
            test_symbol = provider.get_test_symbol()
            
            # 验证返回正确的测试符号（平安银行）
            self.assertEqual(test_symbol, '000001.SZ')
    
    def test_get_index_prices_unavailable(self):
        """测试在不可用状态下获取数据"""
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value=None):
            provider = TushareDataProvider()
            provider.available = False
            provider.ts_pro = None
            
            # 尝试获取数据应该抛出异常
            with self.assertRaises(RuntimeError) as context:
                provider.get_index_prices('000300.SH', '2023-01-01', '2023-01-10', pd.Timestamp.now())
            
            # 验证错误消息
            self.assertIn('Tushare API not available', str(context.exception))
    
    @patch('tushare.pro_api')
    @patch('tushare.set_token')
    def test_get_index_prices_success(self, mock_set_token, mock_pro_api):
        """测试成功获取指数数据"""
        # Mock Tushare API
        mock_ts_pro = MagicMock()
        mock_pro_api.return_value = mock_ts_pro
        
        # Mock 连接测试
        mock_ts_pro.trade_cal.return_value = pd.DataFrame()
        
        # Mock index_daily 返回数据
        mock_df = pd.DataFrame({
            'trade_date': ['20230103', '20230104', '20230105'],
            'open': [3100.0, 3110.0, 3120.0],
            'high': [3120.0, 3130.0, 3140.0],
            'low': [3090.0, 3100.0, 3110.0],
            'close': [3110.0, 3120.0, 3130.0],
            'vol': [1000000, 1100000, 1200000]
        })
        mock_ts_pro.index_daily.return_value = mock_df
        
        # 💚 从配置文件提供 token
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value="test_token"):
            provider = TushareDataProvider()
            
            result = provider.get_index_prices('000300.SH', '2023-01-03', '2023-01-05', pd.Timestamp.now())
            
            # 验证返回的是 PriceData 对象
            self.assertIsInstance(result, PriceData)
            self.assertEqual(result.symbol, '000300.SH')
            self.assertEqual(len(result.records), 3)
            
            # 验证第一条记录
            self.assertIsInstance(result.records[0], OHLCVRecord)
            self.assertEqual(result.records[0].close, 3110.0)
    
    @patch('tushare.pro_api')
    @patch('tushare.set_token')
    def test_get_stock_prices_success(self, mock_set_token, mock_pro_api):
        """测试成功获取个股数据"""
        mock_ts_pro = MagicMock()
        mock_pro_api.return_value = mock_ts_pro
        mock_ts_pro.trade_cal.return_value = pd.DataFrame()
        
        # Mock daily 返回数据
        mock_df = pd.DataFrame({
            'trade_date': ['20230103', '20230104'],
            'open': [10.0, 10.5],
            'high': [10.5, 11.0],
            'low': [9.8, 10.2],
            'close': [10.3, 10.8],
            'vol': [500000, 550000]
        })
        mock_ts_pro.daily.return_value = mock_df
        
        # 💚 从配置文件提供 token
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value="test_token"):
            provider = TushareDataProvider()
            
            result = provider.get_stock_prices('000001.SZ', '2023-01-03', '2023-01-04', pd.Timestamp.now())
            
            # 验证返回的是 PriceData 对象
            self.assertIsInstance(result, PriceData)
            self.assertEqual(result.symbol, '000001.SZ')
            self.assertEqual(len(result.records), 2)


class TushareProviderDataStandardizationTest(unittest.TestCase):
    """测试数据标准化功能"""
    
    def test_standardize_format_empty_data(self):
        """测试空数据标准化"""
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value=None):
            provider = TushareDataProvider()
            
            empty_df = pd.DataFrame()
            result = provider._standardize_format(empty_df, 'TEST')
            
            self.assertIsInstance(result, PriceData)
            self.assertEqual(result.symbol, 'TEST')
            self.assertEqual(len(result.records), 0)
    
    def test_standardize_format_valid_data(self):
        """测试有效数据标准化"""
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value=None):
            provider = TushareDataProvider()
            
            df = pd.DataFrame({
                'trade_date': ['20230103', '20230102', '20230101'],  # 乱序
                'open': [100.0, 99.0, 98.0],
                'high': [102.0, 101.0, 100.0],
                'low': [98.0, 97.0, 96.0],
                'close': [101.0, 100.0, 99.0],
                'vol': [1000, 1100, 1200]
            })
            
            result = provider._standardize_format(df, 'STOCK')
            
            # 验证数据已排序（按时间升序）
            self.assertEqual(len(result.records), 3)
            self.assertEqual(result.records[0].close, 99.0)  # 20230101
            self.assertEqual(result.records[1].close, 100.0)  # 20230102
            self.assertEqual(result.records[2].close, 101.0)  # 20230103


class TushareProviderErrorHandlingTest(unittest.TestCase):
    """测试错误处理"""
    
    # 💚 不再使用 os.environ
    @patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config')
    def test_import_error_handling(self, mock_load_token):
        """测试 tushare 未安装时的错误处理"""
        mock_load_token.return_value = None
        
        # Mock 导入错误
        with patch('builtins.__import__') as mock_import:
            def import_side_effect(name, *args, **kwargs):
                if name == 'tushare':
                    raise ImportError("No module named 'tushare'")
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            provider = TushareDataProvider()
            
            # 验证 API 不可用
            self.assertFalse(provider.available)
            self.assertIsNone(provider.ts_pro)
    
    @patch('tushare.set_token', side_effect=Exception("Connection error"))
    @patch.dict(os.environ, {"TUSHARE_TOKEN": "test_token"})
    def test_initialization_error_handling(self, mock_set_token):
        """测试初始化失败的错误处理"""
        with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value=None):
            provider = TushareDataProvider()
            
            # 验证即使初始化失败，实例也能创建
            self.assertIsNotNone(provider)
            self.assertFalse(provider.available)


class TushareProviderTestMethodTest(unittest.TestCase):
    """测试 test_provider 和 initialize 方法"""
    
    @patch('tushare.pro_api')
    @patch('tushare.set_token')
    def test_initialize_method(self, mock_set_token, mock_pro_api):
        """测试 initialize 方法"""
        mock_ts_pro = MagicMock()
        mock_pro_api.return_value = mock_ts_pro
        mock_ts_pro.trade_cal.return_value = pd.DataFrame()
        
        with patch.dict(os.environ, {}, clear=True):
            with patch('core.data.providers.tushare_provider.TushareDataProvider._load_token_from_config', return_value=None):
                provider = TushareDataProvider()
                
                # 初始状态不可用
                self.assertFalse(provider.available)
                self.assertIsNone(provider.ts_pro)
                
                # 调用 initialize 方法
                provider.initialize(credential="test_credential_token")
                
                # 验证初始化成功
                mock_set_token.assert_called_with("test_credential_token")
                self.assertTrue(provider.available)
                self.assertIsNotNone(provider.ts_pro)
    
    def test_provider_test_method(self):
        """测试 test_provider 类方法"""
        # Mock ConfigManager 返回包含 tushare 配置
        with patch('core.data.providers.base_provider.ConfigManager') as MockConfigManager:
            mock_config_instance = MockConfigManager.return_value
            mock_data_config = Mock()
            mock_data_config.providers = [
                {
                    'id': 'tushare',
                    'name': 'Tushare',
                    'adapter_module': 'core.data.providers.tushare_provider',
                    'adapter_class': 'TushareDataProvider'
                }
            ]
            mock_config_instance.get_provider_config.return_value = mock_data_config
            
            # 测试 test_provider（不会真正调用 API，因为没有真实凭证）
            result = TushareDataProvider.test_provider('tushare', credential='test_token')
            
            # 验证返回结构
            self.assertIn('status', result)
            self.assertIn('test_result', result)
            self.assertIn('available', result)
            self.assertIn('message', result)


if __name__ == '__main__':
    unittest.main()
