"""
分时数据集成测试 - 验证前后端完整链路

测试链路：
API endpoint -> ChartDataAssembler -> DataProvider (AKShare) -> 真实/缓存数据
"""

import unittest

import pandas as pd

from app.chart_data import ChartDataAssembler
from core.data.providers.akshare_provider import AKShareDataProvider


class TestIntradayIntegration(unittest.TestCase):
    """分时数据集成测试"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
        # 不需要indicator_service，因为分时数据不涉及技术指标
        self.assembler = ChartDataAssembler(
            data_provider=self.provider,
            indicator_service=None
        )
        
    def test_full_chain_with_mock_data(self):
        """测试完整链路（使用模拟数据）"""
        # 调用组装器
        result = self.assembler.assemble_intraday_data(
            symbol='000300.SH',
            trade_date=pd.Timestamp.now().strftime('%Y-%m-%d')
        )
        
        # 验证返回结构
        self.assertIsInstance(result, dict)
        self.assertIn('symbol', result)
        self.assertIn('name', result)
        self.assertIn('current_price', result)
        self.assertIn('yesterday_close', result)
        self.assertIn('change', result)
        self.assertIn('change_percent', result)
        self.assertIn('times', result)
        self.assertIn('prices', result)
        self.assertIn('volumes', result)
        self.assertIn('avg_prices', result)
        self.assertIn('order_book', result)
        self.assertIn('trade_records', result)
        
        # 验证数据类型
        self.assertEqual(result['symbol'], '000300.SH')
        self.assertIsInstance(result['times'], list)
        self.assertIsInstance(result['prices'], list)
        self.assertIsInstance(result['volumes'], list)
        self.assertIsInstance(result['order_book'], dict)
        self.assertIn('bids', result['order_book'])
        self.assertIn('asks', result['order_book'])
        
    def test_caching_mechanism(self):
        """测试缓存机制"""
        symbol = '000300.SH'
        trade_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        
        # 第一次调用
        result1 = self.assembler.assemble_intraday_data(symbol, trade_date)
        
        # 第二次调用（应从缓存读取）
        result2 = self.assembler.assemble_intraday_data(symbol, trade_date)
        
        # 验证数据一致性
        self.assertEqual(result1['current_price'], result2['current_price'])
        self.assertEqual(len(result1['times']), len(result2['times']))
        

class TestIntradayAPIEndpoint(unittest.TestCase):
    """分时数据API端点测试"""
    
    def setUp(self):
        """测试前准备"""
        from app.api_service import DataQualityAPIService
        
        # 创建API服务
        self.api_service = DataQualityAPIService()
        self.client = self.api_service.app.test_client()
        
    def test_api_endpoint_success(self):
        """测试API端点成功响应"""
        response = self.client.get('/api/v1/intraday/data?symbol=000300.SH')
        
        # 验证响应
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertIn('timestamp', data)
        
        # 验证数据结构
        intraday = data['data']
        self.assertIn('symbol', intraday)
        self.assertIn('current_price', intraday)
        self.assertIn('times', intraday)
        
    def test_api_endpoint_missing_symbol(self):
        """测试缺少symbol参数"""
        response = self.client.get('/api/v1/intraday/data')
        
        # 验证错误响应
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        
        self.assertEqual(data['status'], 'error')
        self.assertIn('MISSING_PARAMETER', data['error_code'])
        

if __name__ == '__main__':
    unittest.main()
