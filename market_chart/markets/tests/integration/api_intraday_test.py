"""
集成测试：测试分时数据API端到端流程

测试覆盖：
1. API层正确处理ValueError（盘后数据不完整）
2. API层正确返回完整数据
3. 字段命名正确（is_index, trading_phase）
"""
import os
import sys
import unittest

from unittest.mock import Mock, patch

import pandas as pd

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.api_service import DataQualityAPIService
from core.data.providers.akshare_provider import AKShareDataProvider
from core.share.market.market_enums import TradingPhase


class IntradayAPITest(unittest.TestCase):
    """测试分时数据API"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建API服务
        self.api_service = DataQualityAPIService()
        self.client = self.api_service.app.test_client()
        
        # Mock AKShare provider
        self.mock_provider = Mock(spec=AKShareDataProvider)
        
    def test_api_returns_400_when_data_incomplete(self):
        """测试：盘后数据不完整时，API返回400错误"""
        # Mock AKShare 返回不完整数据（只有4个点）
        with patch('core.data.providers.akshare_provider.AKShareDataProvider') as MockProvider:
            mock_instance = MockProvider.return_value
            mock_instance.available = True
            mock_instance.ak = Mock()
            
            # 模拟返回不完整数据
            mock_df = pd.DataFrame({
                '时间': ['2025-12-19 09:30', '2025-12-19 10:00', '2025-12-19 14:30', '2025-12-19 15:00'],
                '收盘': [10.5, 10.6, 10.7, 10.8],
                '成交量': [1000, 1500, 1200, 1300],
                '涨跌额': [0.1, 0.2, 0.3, 0.4]
            })
            mock_instance.ak.stock_zh_a_hist_min_em = Mock(return_value=mock_df)
            
            # 冻结时间到盘后
            with patch('core.data.providers.akshare_provider.dt') as mock_dt:
                mock_dt.now.return_value = datetime(2025, 12, 19, 18, 0, 0)
                mock_dt.strptime = datetime.strptime
                
                # 发送API请求
                response = self.client.get('/api/v1/intraday/data?symbol=600030.SH&trade_date=2025-12-19')
                
                # 验证返回400错误
                self.assertEqual(response.status_code, 400, "盘后数据不完整应返回400")
                
                data = response.get_json()
                self.assertEqual(data['status'], 'error')
                self.assertEqual(data['error_code'], 'DATA_VALIDATION_FAILED')
                self.assertIn('盘后数据不完整', data['message'])
    
    def test_api_returns_200_when_data_complete(self):
        """测试：盘后数据完整时，API返回200"""
        # Mock AKShare 返回完整数据（270个点）
        with patch('core.data.providers.akshare_provider.AKShareDataProvider') as MockProvider:
            mock_instance = MockProvider.return_value
            mock_instance.available = True
            mock_instance.ak = Mock()
            
            # 生成完整的270分钟数据
            time_list = []
            price_list = []
            volume_list = []
            change_list = []
            
            # 生成9:30-12:00（150分钟）
            for i in range(150):
                hour = 9 + (30 + i) // 60
                minute = (30 + i) % 60
                time_list.append(f'2025-12-19 {hour:02d}:{minute:02d}')
                price_list.append(10.0 + i * 0.01)
                volume_list.append(1000 + i * 10)
                change_list.append(i * 0.001)
            
            # 生成13:00-15:00（120分钟）
            for i in range(120):
                hour = 13 + i // 60
                minute = i % 60
                time_list.append(f'2025-12-19 {hour:02d}:{minute:02d}')
                price_list.append(11.5 + i * 0.01)
                volume_list.append(2000 + i * 10)
                change_list.append(1.5 + i * 0.001)
            
            mock_df = pd.DataFrame({
                '时间': time_list,
                '收盘': price_list,
                '成交量': volume_list,
                '涨跌额': change_list
            })
            mock_instance.ak.stock_zh_a_hist_min_em = Mock(return_value=mock_df)
            
            # 冻结时间到盘后
            with patch('core.data.providers.akshare_provider.dt') as mock_dt:
                mock_dt.now.return_value = datetime(2025, 12, 19, 18, 0, 0)
                mock_dt.strptime = datetime.strptime
                
                # 发送API请求
                response = self.client.get('/api/v1/intraday/data?symbol=600030.SH&trade_date=2025-12-19')
                
                # 验证返回200成功
                self.assertEqual(response.status_code, 200, "盘后数据完整应返回200")
                
                data = response.get_json()
                self.assertEqual(data['status'], 'success')
                
                # 验证返回的字段
                self.assertIn('data', data)
                intraday_data = data['data']
                
                # 验证新字段
                self.assertIn('is_index', intraday_data, "应包含is_index字段")
                self.assertIn('trading_phase', intraday_data, "应包含trading_status字段")
                self.assertEqual(intraday_data['trading_phase'], TradingPhase.AFTER_CLOSE.value, "应标记为盘后状态")
                
                # 验证数据完整性
                self.assertEqual(len(intraday_data['times']), 270, "应返回完整的270个tick")
                self.assertEqual(len(intraday_data['prices']), 270)
                self.assertEqual(len(intraday_data['volumes']), 270)
    
    def test_api_before_open_returns_empty_ticks(self):
        """测试：集合竞价时段返回空的ticks"""
        # 冻结时间到集合竞价时段
        with patch('core.data.providers.akshare_provider.dt') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 12, 19, 9, 15, 0)
            mock_dt.strptime = datetime.strptime
            
            # 发送API请求
            response = self.client.get('/api/v1/intraday/data?symbol=600030.SH&trade_date=2025-12-19')
            
            # 验证返回200成功
            self.assertEqual(response.status_code, 200)
            
            data = response.get_json()
            self.assertEqual(data['status'], 'success')
            
            # 验证分时图为空
            intraday_data = data['data']
            self.assertEqual(len(intraday_data['times']), 0, "集合竞价时段应清空分时图")
            self.assertEqual(intraday_data['trading_phase'], TradingPhase.BEFORE_OPEN.value, "应标记为集合竞价状态")


if __name__ == '__main__':
    unittest.main()
