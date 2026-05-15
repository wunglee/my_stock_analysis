"""
测试AKShare数据提供者的插值功能
"""

import unittest
from unittest.mock import patch
from core.data.providers.protocols import IntradayTickRecord
from core.data.providers.akshare_provider import AKShareDataProvider


class TestInterpolationBasic(unittest.TestCase):
    """测试插值基础功能"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
    
    def test_interpolate_empty_list(self):
        """测试空列表插值"""
        result = self.provider._interpolate_to_5_seconds([])
        self.assertEqual(len(result), 0)
    
    def test_interpolate_single_tick(self):
        """测试单个tick插值（应返回原数据）"""
        ticks = [IntradayTickRecord(time='09:30:00', price=100.0, volume=1000, avg_price=100.0)]
        result = self.provider._interpolate_to_5_seconds(ticks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].price, 100.0)
    
    def test_interpolate_consecutive_minutes(self):
        """测试连续分钟的插值"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1200, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=102.0, volume=1200, avg_price=101.0),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证数据点数量：原始2个 + 中间11个插值点 = 13个
        self.assertEqual(len(result), 13)
        
        # 验证第一个点（原始数据）
        self.assertEqual(result[0].time, '09:30:00')
        self.assertEqual(result[0].price, 100.0)
        self.assertEqual(result[0].volume, 1200)
        
        # 验证最后一个点（原始数据）
        self.assertEqual(result[12].time, '09:31:00')
        self.assertEqual(result[12].price, 102.0)
        self.assertEqual(result[12].volume, 1200)
        
        # 验证中间插值点的时间间隔为5秒
        self.assertEqual(result[1].time, '09:30:05')
        self.assertEqual(result[2].time, '09:30:10')
        self.assertEqual(result[11].time, '09:30:55')
    
    def test_interpolate_volume_distribution(self):
        """测试成交量平均分配"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1200, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=102.0, volume=1200, avg_price=101.0),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证成交量平均分配：1200 / 12 = 100
        for i in range(1, 12):  # 中间的11个插值点
            self.assertEqual(result[i].volume, 100)
    
    def test_interpolate_with_gap(self):
        """测试有时间间隔的数据（不应插值超过60秒的间隔）"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1200, avg_price=100.0),
            IntradayTickRecord(time='09:32:00', price=102.0, volume=1200, avg_price=101.0),  # 间隔2分钟
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 由于间隔超过60秒，不应该插值，只保留原始2个点
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].time, '09:30:00')
        self.assertEqual(result[1].time, '09:32:00')
    
    def test_interpolate_preserves_original_points(self):
        """测试插值不改变原始数据点"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1200, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=102.0, volume=1300, avg_price=101.0),
            IntradayTickRecord(time='09:32:00', price=101.0, volume=1100, avg_price=101.5),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 每个原始分钟的数据应该保持不变
        # 09:30:00 在索引0
        self.assertEqual(result[0].price, 100.0)
        self.assertEqual(result[0].volume, 1200)
        
        # 09:31:00 在索引12
        self.assertEqual(result[12].price, 102.0)
        self.assertEqual(result[12].volume, 1300)
        
        # 09:32:00 在索引24
        self.assertEqual(result[24].price, 101.0)
        self.assertEqual(result[24].volume, 1100)


class TestCubicSplineInterpolation(unittest.TestCase):
    """测试三次样条插值的平滑效果"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
    
    def test_cubic_spline_smoothness(self):
        """测试三次样条插值的平滑性"""
        # 创建锯齿数据：100 -> 110 -> 100
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1000, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=110.0, volume=1000, avg_price=105.0),
            IntradayTickRecord(time='09:32:00', price=100.0, volume=1000, avg_price=103.3),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 三次样条插值会产生平滑曲线
        # 验证转折点（09:31:00）仍然是 110.0（保留原始数据点）
        self.assertEqual(result[12].price, 110.0)
        
        # 验证插值点的价格是单调变化的（至少在第一段）
        # 第一段应该从100逐渐增加到110
        for i in range(1, 12):
            self.assertGreater(result[i].price, result[i-1].price, 
                             f"第一段插值应该单调递增，但在索引{i}处违反")
        
        # 第二段应该从110逐渐减少到100
        for i in range(13, 25):
            self.assertLess(result[i].price, result[i-1].price,
                           f"第二段插值应该单调递减，但在索引{i}处违反")
    
    def test_fallback_to_linear_when_scipy_unavailable(self):
        """测试scipy不可用时降级为线性插值"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1200, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=102.0, volume=1200, avg_price=101.0),
        ]
        
        # 使用patch模拟 scipy 不可用
        with patch.dict('sys.modules', {'scipy': None, 'scipy.interpolate': None}):
            result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证仍然生成插值数据
        self.assertEqual(len(result), 13)
        
        # 验证线性插值：中点（09:30:30）应该接近 101.0
        self.assertAlmostEqual(result[6].price, 101.0, places=1)
    
    def test_cubic_spline_with_two_points_fallback(self):
        """测试只有2个点时降级为线性插值"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1200, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=102.0, volume=1200, avg_price=101.0),
        ]
        
        # 即使有scipy，2个点也无法使用三次样条（需要至少3个点）
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证仍然正常插值
        self.assertEqual(len(result), 13)
        
        # 验证第一个和最后一个点保持不变
        self.assertEqual(result[0].price, 100.0)
        self.assertEqual(result[12].price, 102.0)


class TestInterpolationEdgeCases(unittest.TestCase):
    """测试插值的边界情况"""
    
    def setUp(self):
        """测试前准备"""
        self.provider = AKShareDataProvider()
    
    def test_interpolate_with_identical_prices(self):
        """测试价格相同的数据插值"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1000, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=100.0, volume=1000, avg_price=100.0),
            IntradayTickRecord(time='09:32:00', price=100.0, volume=1000, avg_price=100.0),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证所有插值点的价格都是100.0
        for tick in result:
            self.assertEqual(tick.price, 100.0)
    
    def test_interpolate_with_negative_prices(self):
        """测试负价格数据插值（理论场景）"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=-10.0, volume=1000, avg_price=-10.0),
            IntradayTickRecord(time='09:31:00', price=-5.0, volume=1000, avg_price=-7.5),
            IntradayTickRecord(time='09:32:00', price=-2.0, volume=1000, avg_price=-5.0),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证插值正常工作（即使价格为负）
        self.assertEqual(len(result), 25)
        self.assertEqual(result[0].price, -10.0)
        self.assertEqual(result[24].price, -2.0)
    
    def test_interpolate_with_large_volume(self):
        """测试大成交量数据插值"""
        ticks = [
            IntradayTickRecord(time='09:30:00', price=100.0, volume=1000000, avg_price=100.0),
            IntradayTickRecord(time='09:31:00', price=102.0, volume=1200000, avg_price=101.0),
        ]
        
        result = self.provider._interpolate_to_5_seconds(ticks)
        
        # 验证成交量平均分配正确（1000000 / 12 ≈ 83333）
        expected_volume = 1000000 // 12
        for i in range(1, 12):
            self.assertEqual(result[i].volume, expected_volume)


if __name__ == '__main__':
    unittest.main()
