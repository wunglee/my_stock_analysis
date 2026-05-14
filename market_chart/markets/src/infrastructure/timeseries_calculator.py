"""
时序数据统计计算 - 基础设施层

职责：提供与业务无关的纯数学/统计计算函数
- 移动平均（简单、指数、加权）
- 统计指标（标准差、相关性等）
- 时序分析（动量、波动率等）

架构原则：
- 不包含任何业务领域概念（市场、股票、策略等）
- 只接收纯数值数据（Series/DataFrame）
- 参数全部显式传入，不使用业务默认值
- 函数命名使用数学/统计术语，而非金融术语

修订历史:
- 重构为纯技术层，移除业务概念
- 修正RSI使用Wilder平滑法
- 完善ADX返回完整指标组
- 增加边界条件处理
"""

import logging
import warnings
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger('Infrastructure.TimeSeriesCalculator')


class TimeSeriesCalculator:
    """通用技术指标计算器"""
    
    @staticmethod
    def safe_divide(numerator: pd.Series, denominator: pd.Series, 
                   default: float = np.nan) -> pd.Series:
        """
        安全除法，处理除零情况
        
        Args:
            numerator: 分子
            denominator: 分母
            default: 除零时的默认值
        
        Returns:
            除法结果
        """
        # 先计算，然后处理无穷大和NaN
        result = numerator / denominator
        # 将除零0产生的inf替换为default
        result = result.replace([np.inf, -np.inf], default)
        return result
    
    @staticmethod
    def validate_input(prices: pd.Series, min_length: int, name: str = 'prices') -> None:
        """
        验证输入数据
        
        Args:
            prices: 价格序列
            min_length: 最小长度要求
            name: 数据名称
        
        Raises:
            ValueError: 数据不满足要求时
        """
        if prices is None or len(prices) == 0:
            raise ValueError(f"{name} 不能为空")
        
        if len(prices) < min_length:
            warnings.warn(f"{name} 长度({len(prices)})小于推荐最小值({min_length})，"
                        f"前{min_length-1}个结果将为NaN")
    
    @staticmethod
    def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
        """计算简单移动平均"""
        return prices.rolling(window=period).mean()
    
    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
        """计算指数移动平均"""
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_dual_ema_oscillator(values: pd.Series,
                                      fast_period: int,
                                      slow_period: int,
                                      signal_period: int,
                                      histogram_multiplier: float = 1.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算双EMA震荡器（通用算法，无业务概念）
        
        算法：
        1. 快线 = EMA(values, fast_period)
        2. 慢线 = EMA(values, slow_period)
        3. 主线 = 快线 - 慢线
        4. 信号线 = EMA(主线, signal_period)
        5. 柱状图 = (主线 - 信号线) × histogram_multiplier  # 🔧 支持放大倍数
        
        Args:
            values: 数值序列
            fast_period: 快速EMA周期
            slow_period: 慢速EMA周期
            signal_period: 信号线周期
            histogram_multiplier: 柱状图放大倍数（中国市场习惯用2，国际标准用1）
        
        Returns:
            (主线, 信号线, 柱状图)
        
        Note:
            业务层将此映射为MACD等具体指标
            - 中国标准：histogram_multiplier=2 (DIFF/DEA/MACD柱)
            - 国际标准：histogram_multiplier=1 (MACD/Signal/Histogram)
        """
        ema_fast = TimeSeriesCalculator.calculate_ema(values, fast_period)
        ema_slow = TimeSeriesCalculator.calculate_ema(values, slow_period)
        main_line = ema_fast - ema_slow
        signal_line = main_line.ewm(span=signal_period, adjust=False).mean()
        histogram = (main_line - signal_line) * histogram_multiplier  # 🔧 乘以放大倍数
        return main_line, signal_line, histogram
    
    @staticmethod
    def calculate_momentum_index(values: pd.Series, period: int) -> pd.Series:
        """
        计算动量指数（使用Wilder指数平滑法）
        
        算法：
        1. 计算变化量 delta = values.diff()
        2. 分离正负变化：gain(上涨), loss(下跌)
        3. Wilder平滑：avg_gain, avg_loss (alpha=1/period)
        4. 相对强度 RS = avg_gain / avg_loss
        5. 归一化指数 = 100 - 100/(1+RS)  范围[0,100]
        
        Args:
            values: 数值序列
            period: 平滑周期
        
        Returns:
            动量指数序列（0-100）
        
        Note:
            业务层将此映射为RSI等具体指标
        """
        delta = values.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Wilder平滑法：使用指数加权平均 alpha=1/period
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        # 处理除零情况
        rs = avg_gain / avg_loss.replace(0, np.nan)
        index = 100 - (100 / (1 + rs))
        
        # 确保在0-100范围内
        index = index.clip(0, 100)
        
        return index
    
    @staticmethod
    def calculate_volatility_bands(values: pd.Series,
                                   period: int,
                                   std_multiplier: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算波动率通道（基于移动平均和标准差）
        
        算法：
        1. 中轨 = SMA(values, period)
        2. 标准差 = STD(values, period)
        3. 上轨 = 中轨 + std_multiplier * 标准差
        4. 下轨 = 中轨 - std_multiplier * 标准差
        
        Args:
            values: 数值序列
            period: 移动窗口周期
            std_multiplier: 标准差倍数
        
        Returns:
            (上轨, 中轨, 下轨)
        
        Note:
            业务层将此映射为布林带等具体指标
        """
        middle = values.rolling(window=period).mean()
        std = values.rolling(window=period).std()
        upper = middle + (std_multiplier * std)
        lower = middle - (std_multiplier * std)
        return upper, middle, lower
    
    @staticmethod
    def calculate_true_range_average(high: pd.Series,
                                     low: pd.Series,
                                     previous_close: pd.Series,
                                     period: int) -> pd.Series:
        """
        计算真实范围均值（三值比较法）
        
        算法：
        1. TR = max(high-low, |high-prev_close|, |low-prev_close|)
        2. ATR = SMA(TR, period)
        
        Args:
            high: 高点序列
            low: 低点序列
            previous_close: 前收盘价序列（通常是close.shift()）
            period: 平滑周期
        
        Returns:
            真实范围均值序列
        
        Note:
            业务层将此映射为ATR等波动率指标
        """
        tr1 = high - low
        tr2 = abs(high - previous_close)
        tr3 = abs(low - previous_close)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    
    @staticmethod
    def calculate_range_position(high: pd.Series,
                                low: pd.Series,
                                close: pd.Series,
                                period: int,
                                smooth_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        计算当前值在区间中的相对位置（百分比法）
        
        算法：
        1. lowest = MIN(low, period)
        2. highest = MAX(high, period)
        3. position = 100 * (close - lowest) / (highest - lowest)
        4. smooth_position = SMA(position, smooth_period)
        
        Args:
            high: 高点序列
            low: 低点序列
            close: 当前值序列
            period: 区间周期
            smooth_period: 平滑周期
        
        Returns:
            (原始位置, 平滑位置)
        
        Note:
            业务层将此映射为随机指标(KDJ)等
        """
        lowest = low.rolling(window=period).min()
        highest = high.rolling(window=period).max()
        position = 100 * (close - lowest) / (highest - lowest)
        smooth_position = position.rolling(window=smooth_period).mean()
        return position, smooth_position
    
    @staticmethod
    def calculate_directional_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        计算方向性成交量累计
        
        算法：
        1. direction = sign(close.diff())  # +1, 0, -1
        2. directional_vol = direction * volume
        3. cumulative = cumsum(directional_vol)
        
        Args:
            close: 当前值序列
            volume: 成交量序列
        
        Returns:
            累积方向性成交量
        
        Note:
            业务层将此映射为OBV等成交量指标
        """
        directional = (np.sign(close.diff()) * volume).fillna(0)
        cumulative = directional.cumsum()
        return cumulative
    
    @staticmethod
    def calculate_directional_indicators(high: pd.Series,
                                        low: pd.Series,
                                        close: pd.Series,
                                        period: int) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算方向性指标系统（Wilder法）
        
        算法：
        1. 计算方向移动：+DM, -DM
        2. 计算真实范围：TR
        3. Wilder平滑：+DI = 100*EWM(+DM)/EWM(TR)
        4. Wilder平滑：-DI = 100*EWM(-DM)/EWM(TR)
        5. 方向性指数：DX = 100*|+DI - -DI| / (+DI + -DI)
        6. 平均方向性指数：ADX = EWM(DX)
        
        Args:
            high: 高点序列
            low: 低点序列
            close: 当前值序列
            period: Wilder平滑周期
        
        Returns:
            (+DI, -DI, ADX)
        
        Note:
            业务层将此用于趋势强度分析
        """
        # 计算方向移动
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), 
                           index=high.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0),
                            index=high.index)
        
        # 计算真实范围
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Wilder平滑 (alpha=1/period)
        smoothed_tr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        smoothed_plus_dm = plus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        smoothed_minus_dm = minus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        # 计算DI指标
        plus_di = 100 * smoothed_plus_dm / smoothed_tr.replace(0, np.nan)
        minus_di = 100 * smoothed_minus_dm / smoothed_tr.replace(0, np.nan)
        
        # 计算ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        return plus_di, minus_di, adx
    
    @staticmethod
    def calculate_vwap(typical_price: pd.Series,
                      volume: pd.Series,
                      reset_period: str = 'D') -> pd.Series:
        """
        计算成交量加权平均价（纯数学算法）
        
        算法：
        1. 累计价量积 = cumsum(typical_price * volume)
        2. 累计成交量 = cumsum(volume)
        3. VWAP = 累计价量积 / 累计成交量
        4. 按reset_period周期重置累计（支持'D'日、'W'周等）
        
        Args:
            typical_price: 典型价格序列（已由业务层计算）
            volume: 成交量序列
            reset_period: 重置周期（'D'日、'W'周、'M'月等）
        
        Returns:
            VWAP值序列
        
        Note:
            业务层负责计算typical_price和处理交易时段（午休等）
        """
        # 计算价量积
        price_volume = typical_price * volume
        
        if reset_period and isinstance(typical_price.index, pd.DatetimeIndex):
            # 按周期分组累计
            pv_cumsum = price_volume.groupby(pd.Grouper(freq=reset_period)).cumsum()
            vol_cumsum = volume.groupby(pd.Grouper(freq=reset_period)).cumsum()
        else:
            # 全局累计
            pv_cumsum = price_volume.cumsum()
            vol_cumsum = volume.cumsum()
        
        # 计算VWAP，处理除零
        vwap = pv_cumsum / vol_cumsum.replace(0, np.nan)
        
        return vwap
    
    @staticmethod
    def calculate_commodity_channel_index(high: pd.Series,
                                         low: pd.Series,
                                         close: pd.Series,
                                         period: int,
                                         constant: float = 0.015) -> pd.Series:
        """
        计算商品通道指数（纯数学算法）
        
        算法：
        1. 典型价格 TP = (high + low + close) / 3
        2. 移动平均 SMA = SMA(TP, period)
        3. 平均绝对偏差 MAD = mean(|TP - SMA|)
        4. CCI = (TP - SMA) / (constant * MAD)
        
        Args:
            high: 高点序列
            low: 低点序列
            close: 收盘价序列
            period: 计算周期
            constant: 常数因子（通常0.015）
        
        Returns:
            CCI值序列
        
        Note:
            业务层将此映射为CCI指标，并定义超买超卖区域
        """
        # 计算典型价格
        typical_price = (high + low + close) / 3
        
        # SMA
        sma = typical_price.rolling(window=period).mean()
        
        # 平均绝对偏差 (Mean Absolute Deviation)
        mad = typical_price.rolling(window=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))),
            raw=True
        )
        
        # 计算CCI，处理除零
        cci = (typical_price - sma) / (constant * mad.replace(0, np.nan))
        
        return cci
