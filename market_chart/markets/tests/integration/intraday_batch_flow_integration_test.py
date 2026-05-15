"""
分时图批次增量流程集成测试

测试范围：
- 前端请求 → API路由 → ChartDataAssembler → DataProvider → 数据生成
- 验证批次序号机制是否正确工作
- 验证增量数据是否真正不同

测试策略：
- 模拟前端发送不同批次序号
- 验证后端返回的数据确实不同
- 验证批次序号递增时数据也在变化
"""

import json
import unittest

from app.api_service import DataQualityAPIService
from core.share.config_manager import ConfigManager


class IntradayBatchFlowIntegrationTest(unittest.TestCase):
    """分时图批次增量流程集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        # 创建配置管理器
        cls.config_manager = ConfigManager()
        
        # 创建API服务
        cls.api_service = DataQualityAPIService(cls.config_manager)
        cls.app = cls.api_service.app
        cls.client = cls.app.test_client()
    
    def test_batch_indices_different_data(self):
        """测试：不同批次序号返回不同的数据（盘中模式）"""
        symbol = '600036.SH'
        
        # 第1次请求：批次序号 [1, 2, 3]
        response1 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps([{"index": 1, "timestamp": 1000}, {"index": 2, "timestamp": 1001}, {"index": 3, "timestamp": 1002}])}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response1.status_code, 200)
        data1 = response1.get_json()
        
        # 第2次请求：批次序号 [4, 5, 6]
        response2 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps([{"index": 4, "timestamp": 1003}, {"index": 5, "timestamp": 1004}, {"index": 6, "timestamp": 1005}])}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.get_json()
        
        # 验证返回成功
        self.assertEqual(data1['status'], 'success')
        self.assertEqual(data2['status'], 'success')
        
        # 验证返回的tick数量：3个批次 × 12个tick = 36个tick（盘中模式）
        times1 = data1['data']['times']
        times2 = data2['data']['times']
        self.assertEqual(len(times1), 36, "批次[1,2,3]应返回36个tick")
        self.assertEqual(len(times2), 36, "批次[4,5,6]应返回36个tick")
        
        # 验证时间范围不同
        self.assertNotEqual(times1[0], times2[0], "不同批次的起始时间应不同")
        self.assertNotEqual(times1[-1], times2[-1], "不同批次的结束时间应不同")
        
        # 验证价格数据不同（由于使用批次序号作为随机种子）
        prices1 = data1['data']['prices']
        prices2 = data2['data']['prices']
        self.assertNotEqual(prices1, prices2, "不同批次的价格数据应不同")
        
        print(f"✅ 批次[1,2,3]时间范围: {times1[0]} - {times1[-1]}")
        print(f"✅ 批次[4,5,6]时间范围: {times2[0]} - {times2[-1]}")
        print(f"✅ 价格差异验证通过")
    
    def test_incremental_batch_progression(self):
        """测试：模拟前端增量请求，验证批次递增"""
        symbol = '600036.SH'
        
        # 模拟前端逻辑：首次加载空批次，后端返回开盘至今的数据（根据当前时间计算）
        response_initial = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps([])}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response_initial.status_code, 200)
        data_initial = response_initial.get_json()
        self.assertEqual(data_initial['status'], 'success')
        
        # 验证首次加载返回数据（tick数量根据当前时间动态计算）
        times_initial = data_initial['data']['times']
        self.assertGreater(len(times_initial), 0, "首次加载应返回至少1个tick")
        
        print(f"✅ 首次加载: {len(times_initial)}个tick, 时间范围: {times_initial[0]} - {times_initial[-1]}")
        
        # 模拟增量更新：请求下一个批次（假设当前批次序号为100）
        current_batch = 100
        batches_inc1 = [{"index": current_batch, "timestamp": 2000}]
        response_inc1 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches_inc1)}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response_inc1.status_code, 200)
        data_inc1 = response_inc1.get_json()
        
        # 验证增量返回1批次的数据：1 × 12 = 12个tick
        times_inc1 = data_inc1['data']['times']
        self.assertEqual(len(times_inc1), 12, "增量更新应返回12个tick（1个批次）")
        
        print(f"✅ 增量批次{current_batch}: {len(times_inc1)}个tick, 时间范围: {times_inc1[0]} - {times_inc1[-1]}")
        
        # 再次增量：请求下下个批次
        current_batch = 101
        batches_inc2 = [{"index": current_batch, "timestamp": 2001}]
        response_inc2 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches_inc2)}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response_inc2.status_code, 200)
        data_inc2 = response_inc2.get_json()
        
        times_inc2 = data_inc2['data']['times']
        self.assertEqual(len(times_inc2), 12, "第二次增量更新应返回12个tick")
        
        # 验证两次增量的时间范围不同
        self.assertNotEqual(times_inc1[0], times_inc2[0], "不同批次的时间应不同")
        
        print(f"✅ 增量批次{current_batch}: {len(times_inc2)}个tick, 时间范围: {times_inc2[0]} - {times_inc2[-1]}")
        print(f"✅ 增量递进验证通过")
    
    def test_multiple_batches_sequential(self):
        """测试：请求多个连续批次，验证数据连续性"""
        symbol = '600036.SH'
        
        # 请求批次 [10, 11, 12]
        batches = [{"index": 10, "timestamp": 3000}, {"index": 11, "timestamp": 3001}, {"index": 12, "timestamp": 3002}]
        response = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches)}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        
        times = data['data']['times']
        prices = data['data']['prices']
        
        # 验证返回36个tick（3批次 × 12）
        self.assertEqual(len(times), 36)
        self.assertEqual(len(prices), 36)
        
        # 验证时间是递增的（连续批次应该时间连续）
        for i in range(1, len(times)):
            self.assertGreater(times[i], times[i-1], f"时间应递增: {times[i]} > {times[i-1]}")
        
        # 验证每12个tick对应一个批次（批次内时间间隔5秒）
        # 批次10: times[0:12]
        # 批次11: times[12:24]
        # 批次12: times[24:36]
        
        print(f"✅ 批次[10,11,12]返回{len(times)}个tick")
        print(f"✅ 时间范围: {times[0]} - {times[-1]}")
        print(f"✅ 时间连续性验证通过")
    
    def test_api_parameter_validation(self):
        """测试：API参数验证"""
        symbol = '600036.SH'
        
        # 测试1：batches缺少必需字段
        batches_invalid = [{"index": 1}]  # 缺少timestamp字段
        response1 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches_invalid)}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response1.status_code, 400)
        data1 = response1.get_json()
        self.assertEqual(data1['status'], 'error')
        self.assertIn('必须包含', data1['message'])
        
        print(f"✅ 批次字段缺失验证通过: {data1['message']}")
        
        # 测试2：无效的JSON格式
        response2 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches=invalid_json&'
            f'trading_phase=trading'
        )
        self.assertEqual(response2.status_code, 400)
        data2 = response2.get_json()
        self.assertEqual(data2['status'], 'error')
        self.assertIn('无效的JSON', data2['message'])
        
        print(f"✅ 无效JSON验证通过: {data2['message']}")
        
        # 测试3：无效的trading_phase
        batches_valid = [{"index": 1, "timestamp": 1000}]
        response3 = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches_valid)}&'
            f'trading_phase=invalid_mode'
        )
        self.assertEqual(response3.status_code, 400)
        data3 = response3.get_json()
        self.assertEqual(data3['status'], 'error')
        self.assertIn('trading_phase', data3['message'])
        
        print(f"✅ 无效模式验证通过: {data3['message']}")
    
    def test_empty_batch_indices_returns_initial_data(self):
        """测试：空批次序号应返回初始数据（根据当前时间计算开盘至今）"""
        symbol = '600036.SH'
        
        response = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps([])}&'
            f'trading_phase=trading'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        
        times = data['data']['times']
        # 应返回开盘至今的数据（tick数量根据当前时间动态计算）
        self.assertGreater(len(times), 0, "空批次应返回开盘至今数据（至少1个tick）")
        
        print(f"✅ 空批次序号返回初始数据: {len(times)}个tick")
        print(f"✅ 时间范围: {times[0]} - {times[-1]}")
    
    def test_before_open_mode(self):
        """测试：盘前模式（有批次时生成tick用于轮询盘口）"""
        symbol = '600036.SH'
        
        batches = [{"index": 1, "timestamp": 1000}, {"index": 2, "timestamp": 1001}]
        response = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches)}&'
            f'trading_phase=before_open'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        
        # 盘前模式有批次时应生成tick（用于轮询盘口）：2批次 × 12 = 24个tick
        times = data['data']['times']
        self.assertEqual(len(times), 24, "盘前模式有批次时应生成24个tick（2批次 × 12）")
        
        # 应该有盘口数据（非指数时）
        order_book = data['data']['order_book']
        self.assertIn('bids', order_book)
        self.assertIn('asks', order_book)
        
        print(f"✅ 盘前模式: {len(times)}个tick")
        print(f"✅ 盘口数据存在: 买盘{len(order_book['bids'])}档, 卖盘{len(order_book['asks'])}档")
    
    def test_after_close_mode(self):
        """测试：盘后模式（忽略批次参数，始终返回全天数据）"""
        symbol = '600036.SH'
        
        # 盘后模式请求多个批次（但批次参数应被忽略）
        batches = [{"index": i, "timestamp": 1000+i} for i in range(10)]
        response = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches)}&'
            f'trading_phase=after_close'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        
        times = data['data']['times']
        # 盘后模式忽略batches参数，始终返回全天330个批次的数据（跳过午休30分钟）
        # 上午120批次（09:30-11:30），下午180批次（13:00-15:60）= 300批次 × 12 = 3600个tick
        # 注意：实际代码中午休时段会被跳过
        expected_ticks = 300 * 12  # 300批次（不含午休）
        self.assertEqual(len(times), expected_ticks, f"盘后模式应返回全天数据（{expected_ticks}个tick）")
        
        print(f"✅ 盘后模式: {len(times)}个tick")
        print(f"✅ 时间范围: {times[0]} - {times[-1]}")
    
    def test_trading_phase_data_generation(self):
        """测试：不同交易时段的数据生成差异"""
        symbol = '600036.SH'
        batch_count = 3
        batches = [{"index": i, "timestamp": 1000+i} for i in range(batch_count)]
        
        # 盘中模式：每批次12个tick
        resp_intraday = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches)}&'
            f'trading_phase=trading'
        )
        data_intraday = resp_intraday.get_json()['data']
        
        # 盘前模式：有批次时每批次12个tick（用于轮询盘口）
        resp_before = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches)}&'
            f'trading_phase=before_open'
        )
        data_before = resp_before.get_json()['data']
        
        # 盘后模式：忽略batches参数，返回全天数据（300批次 × 12 = 3600tick）
        resp_after = self.client.get(
            f'/api/v1/intraday/data?symbol={symbol}&'
            f'batches={json.dumps(batches)}&'
            f'trading_phase=after_close'
        )
        data_after = resp_after.get_json()['data']
        
        # 验证
        self.assertEqual(len(data_intraday['times']), 36, "盘中: 3批次 × 12 = 36tick")
        self.assertEqual(len(data_before['times']), 36, "盘前: 3批次 × 12 = 36tick（轮询盘口）")
        self.assertEqual(len(data_after['times']), 3600, "盘后: 300批次 × 12 = 3600tick（全天数据）")
        
        print(f"✅ 盘中模式: {len(data_intraday['times'])}tick")
        print(f"✅ 盘前模式: {len(data_before['times'])}tick")
        print(f"✅ 盘后模式: {len(data_after['times'])}tick")


if __name__ == '__main__':
    unittest.main(verbosity=2)
