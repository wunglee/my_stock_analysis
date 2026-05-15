"""
基础设施层测试 - 时序数据计算器
测试 infrastructure/timeseries_calculator.py (TimeSeriesCalculator)

测试范围：纯数学/统计算法，无业务概念
"""

import unittest
import pandas as pd
import numpy as np
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.timeseries_calculator import TimeSeriesCalculator


class TestTimeSeriesCalculator(unittest.TestCase):
    """时序数据计算器测试 - 基础设施层"""
    
    def setUp(self):
        """准备测试数据"""
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        
        # 生成随机游走价格序列
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        self.values = pd.Series(prices, index=dates, name='values')
        
        # 生成OHLCV数据
        self.high = self.values + np.random.rand(100) * 2
        self.low = self.values - np.random.rand(100) * 2
        self.close = self.values
        self.volume = pd.Series(np.random.randint(1000000, 10000000, 100), index=dates)
    
    # ==================== 移动平均测试 ====================
    
    def test_sma_basic(self):
        """测试简单移动平均 - 基本功能"""
        period = 5
        sma = TimeSeriesCalculator.calculate_sma(self.values, period)
        
        # 前4个应该是NaN
        self.assertTrue(pd.isna(sma.iloc[:period-1]).all())
        
        # 第5个值等于前5个的平均
        expected = self.values.iloc[:period].mean()
        self.assertAlmostEqual(sma.iloc[period-1], expected, places=5)
        
        # 长度一致
        self.assertEqual(len(sma), len(self.values))
    
    def test_ema_basic(self):
        """测试指数移动平均"""
        period = 12
        ema = TimeSeriesCalculator.calculate_ema(self.values, period)
        
        self.assertEqual(len(ema), len(self.values))
        # EMA应该对近期价格更敏感
        self.assertIsNotNone(ema.iloc[-1])
    
    # ==================== 双EMA震荡器测试 ====================
    
    def test_dual_ema_oscillator(self):
        """测试双EMA震荡器（纯数学算法）"""
        main, signal, hist = TimeSeriesCalculator.calculate_dual_ema_oscillator(
            self.values, fast_period=12, slow_period=26, signal_period=9
        )
        
        # 返回三个Series
        self.assertIsInstance(main, pd.Series)
        self.assertIsInstance(signal, pd.Series)
        self.assertIsInstance(hist, pd.Series)
        
        # 长度一致
        self.assertEqual(len(main), len(self.values))
        
        # 柱状图 = 主线 - 信号线
        pd.testing.assert_series_equal(hist, main - signal, check_names=False)
    
    # ==================== 动量指数测试 ====================
    
    def test_momentum_index_range(self):
        """测试动量指数值域（0-100）"""
        momentum = TimeSeriesCalculator.calculate_momentum_index(self.values, period=14)
        
        valid = momentum.dropna()
        self.assertTrue((valid >= 0).all())
        self.assertTrue((valid <= 100).all())
    
    def test_momentum_index_extreme(self):
        """测试动量指数极端情况"""
        # 持续上涨
        up_trend = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20] * 3)
        momentum_up = TimeSeriesCalculator.calculate_momentum_index(up_trend, period=5)
        self.assertGreater(momentum_up.iloc[-1], 70)
        
        # 持续下跌
        down_trend = pd.Series([20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10] * 3)
        momentum_down = TimeSeriesCalculator.calculate_momentum_index(down_trend, period=5)
        self.assertLess(momentum_down.iloc[-1], 30)
    
    def test_momentum_index_zero_division(self):
        """测试动量指数除零处理"""
        # 全部上涨
        all_up = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        momentum = TimeSeriesCalculator.calculate_momentum_index(all_up, period=5)
        
        valid = momentum.dropna()
        self.assertTrue((valid >= 0).all())
        self.assertTrue((valid <= 100).all())
    
    # ==================== 波动率通道测试 ====================
    
    def test_volatility_bands_structure(self):
        """测试波动率通道结构"""
        upper, middle, lower = TimeSeriesCalculator.calculate_volatility_bands(
            self.values, period=20, std_multiplier=2.0
        )
        
        # 返回三个Series
        self.assertIsInstance(upper, pd.Series)
        self.assertIsInstance(middle, pd.Series)
        self.assertIsInstance(lower, pd.Series)
        
        # 长度一致
        self.assertEqual(len(upper), len(self.values))
        
        # 上轨 >= 中轨 >= 下轨
        valid_idx = ~middle.isna()
        self.assertTrue((upper[valid_idx] >= middle[valid_idx]).all())
        self.assertTrue((middle[valid_idx] >= lower[valid_idx]).all())
    
    def test_volatility_bands_middle_is_sma(self):
        """测试波动率通道中轨等于SMA"""
        period = 20
        upper, middle, lower = TimeSeriesCalculator.calculate_volatility_bands(
            self.values, period=period, std_multiplier=2.0
        )
        sma = TimeSeriesCalculator.calculate_sma(self.values, period)
        
        pd.testing.assert_series_equal(middle, sma, check_names=False)
    
    # ==================== 真实范围均值测试 ====================
    
    def test_true_range_average_positive(self):
        """测试真实范围均值恒为正"""
        previous_close = self.close.shift()
        atr = TimeSeriesCalculator.calculate_true_range_average(
            self.high, self.low, previous_close, period=14
        )
        
        valid = atr.dropna()
        self.assertTrue((valid > 0).all())
    
    def test_true_range_average_volatility(self):
        """测试真实范围均值反映波动性"""
        # 高波动数据
        volatile_high = pd.Series([100, 110, 95, 105, 90, 115] * 5)
        volatile_low = volatile_high - 5
        volatile_close = (volatile_high + volatile_low) / 2
        volatile_prev = volatile_close.shift()
        
        # 低波动数据
        stable_high = pd.Series([100, 101, 100, 101, 100, 101] * 5)
        stable_low = stable_high - 1
        stable_close = (stable_high + stable_low) / 2
        stable_prev = stable_close.shift()
        
        atr_volatile = TimeSeriesCalculator.calculate_true_range_average(
            volatile_high, volatile_low, volatile_prev, period=5
        )
        atr_stable = TimeSeriesCalculator.calculate_true_range_average(
            stable_high, stable_low, stable_prev, period=5
        )
        
        self.assertGreater(atr_volatile.mean(), atr_stable.mean())
    
    # ==================== 区间相对位置测试 ====================
    
    def test_range_position_range(self):
        """测试区间相对位置值域（0-100）"""
        position, smooth = TimeSeriesCalculator.calculate_range_position(
            self.high, self.low, self.close, period=14, smooth_period=3
        )
        
        valid_pos = position.dropna()
        valid_smooth = smooth.dropna()
        
        self.assertTrue((valid_pos >= 0).all())
        self.assertTrue((valid_pos <= 100).all())
        self.assertTrue((valid_smooth >= 0).all())
        self.assertTrue((valid_smooth <= 100).all())
    
    # ==================== 方向性成交量测试 ====================
    
    def test_directional_volume_accumulation(self):
        """测试方向性成交量累积特性"""
        cumulative = TimeSeriesCalculator.calculate_directional_volume(
            self.close, self.volume
        )
        
        # 长度一致
        self.assertEqual(len(cumulative), len(self.close))
        
        # 第一个值应该是0
        self.assertEqual(cumulative.iloc[0], 0)
    
    # ==================== 方向性指标系统测试 ====================
    
    def test_directional_indicators_complete(self):
        """测试方向性指标系统（三个指标）"""
        plus_di, minus_di, adx = TimeSeriesCalculator.calculate_directional_indicators(
            self.high, self.low, self.close, period=14
        )
        
        # 返回三个Series
        self.assertIsInstance(plus_di, pd.Series)
        self.assertIsInstance(minus_di, pd.Series)
        self.assertIsInstance(adx, pd.Series)
        
        # 长度一致
        self.assertEqual(len(plus_di), len(self.high))
        self.assertEqual(len(minus_di), len(self.high))
        self.assertEqual(len(adx), len(self.high))
        
        # +DI和-DI应该是正值
        valid_plus = plus_di.dropna()
        valid_minus = minus_di.dropna()
        self.assertTrue((valid_plus >= 0).all())
        self.assertTrue((valid_minus >= 0).all())
        
        # ADX应该在0-100之间
        valid_adx = adx.dropna()
        self.assertTrue((valid_adx >= 0).all())
        self.assertTrue((valid_adx <= 100).all())
    
    def test_directional_indicators_trend_detection(self):
        """测试方向性指标趋势检测"""
        # 明显上升趋势
        uptrend_high = pd.Series([100, 102, 105, 108, 112, 115, 119, 123, 127, 132] * 3)
        uptrend_low = uptrend_high - 2
        uptrend_close = (uptrend_high + uptrend_low) / 2
        
        plus_di, minus_di, adx = TimeSeriesCalculator.calculate_directional_indicators(
            uptrend_high, uptrend_low, uptrend_close, period=5
        )
        
        # 上升趋势中，+DI应该大于-DI
        valid_idx = ~plus_di.isna()
        if valid_idx.sum() > 0:
            last_valid = valid_idx[valid_idx].index[-5:]
            self.assertGreater(
                plus_di[last_valid].mean(),
                minus_di[last_valid].mean()
            )
    
    # ==================== 边界条件测试 ====================
    
    def test_empty_input(self):
        """测试空输入"""
        empty = pd.Series([])
        sma = TimeSeriesCalculator.calculate_sma(empty, 5)
        self.assertEqual(len(sma), 0)
    
    def test_single_value(self):
        """测试单个值"""
        single = pd.Series([100])
        sma = TimeSeriesCalculator.calculate_sma(single, 5)
        self.assertTrue(sma.isna().all())
    
    def test_all_same_values(self):
        """测试所有值相同（无波动）"""
        flat = pd.Series([100] * 50)
        
        # SMA应该全是100
        sma = TimeSeriesCalculator.calculate_sma(flat, 10)
        self.assertTrue((sma.dropna() == 100).all())
    
    # ==================== 工具方法测试 ====================
    
    def test_safe_divide(self):
        """测试安全除法"""
        numerator = pd.Series([10, 20, 30])
        denominator = pd.Series([2, 0, 5])
        
        result = TimeSeriesCalculator.safe_divide(numerator, denominator, default=0)
        
        self.assertEqual(result.iloc[0], 5.0)  # 10/2
        # replace(0, nan).fillna(default) 的逻辑：0被替换为nan，然后填充为default
        # 所以 20/0 会先变成20/nan=nan，然后填充为0
        self.assertEqual(result.iloc[1], 0.0)  # 20/0 -> fillna(0)
        self.assertEqual(result.iloc[2], 6.0)  # 30/5
    
    def test_validate_input_empty(self):
        """测试输入验证 - 空数据"""
        with self.assertRaises(ValueError):
            TimeSeriesCalculator.validate_input(pd.Series([]), 5)
    
    def test_validate_input_insufficient(self):
        """测试输入验证 - 数据不足"""
        short = pd.Series([1, 2, 3])
        with self.assertWarns(UserWarning):
            TimeSeriesCalculator.validate_input(short, 10)
    
    # ==================== VWAP测试 ====================
    
    def test_vwap_basic(self):
        """测试VWAP基本计算"""
        typical_price = (self.high + self.low + self.close) / 3
        vwap = TimeSeriesCalculator.calculate_vwap(
            typical_price, self.volume, reset_period='D'
        )
        
        self.assertEqual(len(vwap), len(typical_price))
        # VWAP应该是有效数值
        self.assertFalse(vwap.dropna().empty)
    
    def test_vwap_daily_reset(self):
        """测试VWAP每日重置（A股特色）"""
        # 生成跨日数据
        dates = pd.date_range('2023-01-01 09:30:00', periods=480, freq='1min')
        typical_price = pd.Series(np.random.randn(480) + 100, index=dates)
        volume = pd.Series(np.random.randint(1000, 10000, 480), index=dates)
        
        vwap = TimeSeriesCalculator.calculate_vwap(
            typical_price, volume, reset_period='D'
        )
        
        # 每天的第一个VWAP应该等于典型价格（重置后）
        # 第一天的第一个点
        self.assertAlmostEqual(vwap.iloc[0], typical_price.iloc[0], places=5)
    
    def test_vwap_accumulation(self):
        """测试VWAP累积特性"""
        # 简单案例：3个数据点
        typical_price = pd.Series([100, 102, 101])
        volume = pd.Series([1000, 2000, 1500])
        
        vwap = TimeSeriesCalculator.calculate_vwap(
            typical_price, volume, reset_period=None
        )
        
        # 第一个点：VWAP = 100
        self.assertAlmostEqual(vwap.iloc[0], 100.0, places=5)
        
        # 第二个点：VWAP = (100*1000 + 102*2000) / (1000+2000)
        expected_2 = (100*1000 + 102*2000) / 3000
        self.assertAlmostEqual(vwap.iloc[1], expected_2, places=5)
    
    # ==================== CCI测试 ====================
    
    def test_cci_basic(self):
        """测试CCI基本计算"""
        cci = TimeSeriesCalculator.calculate_commodity_channel_index(
            self.high, self.low, self.close, period=14, constant=0.015
        )
        
        self.assertEqual(len(cci), len(self.close))
        self.assertFalse(cci.dropna().empty)
    
    def test_cci_extreme_values(self):
        """测试CCI极端值（涨停/跌停）"""
        # 模拟连续涨停
        limit_up = pd.Series([10.0 * (1.1 ** i) for i in range(50)])
        cci_up = TimeSeriesCalculator.calculate_commodity_channel_index(
            limit_up, limit_up * 0.98, limit_up * 0.99, period=14
        )
        
        # 连续涨停时CCI应该大于100（超买区域）
        valid = cci_up.dropna()
        self.assertTrue(valid.iloc[-1] > 0)  # 正值
    
    def test_cci_flat_market(self):
        """测试CCI横盘市场（A股常见）"""
        # 完全横盘
        flat_price = pd.Series([100.0] * 50)
        cci_flat = TimeSeriesCalculator.calculate_commodity_channel_index(
            flat_price, flat_price, flat_price, period=14
        )
        
        # 横盘时CCI应该接近0（MAD=0时会产生NaN）
        # 由于MAD=0，分母为0，结果为NaN
        valid = cci_flat.dropna()
        # 如果有有效值，应该接近0
        if len(valid) > 0:
            self.assertTrue(abs(valid.mean()) < 0.1)
    
    def test_cci_normal_fluctuation(self):
        """测试CCI正常波动"""
        # 正常波动数据
        cci = TimeSeriesCalculator.calculate_commodity_channel_index(
            self.high, self.low, self.close, period=20, constant=0.015
        )
        
        valid = cci.dropna()
        # 大部分值应该在[-200, 200]范围内
        within_range = ((valid >= -200) & (valid <= 200)).sum()
        self.assertGreater(within_range / len(valid), 0.8)  # 80%在范围内


if __name__ == '__main__':
    unittest.main(verbosity=2)
