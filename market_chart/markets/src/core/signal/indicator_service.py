"""
技术指标业务层封装

职责：将基础设施层的纯数学算法映射为量化交易领域的具体指标
- 定义业务概念（MACD、RSI、布林带等金融术语）
- 管理市场参数（A股、美股不同参数）
- 提供业务友好的接口

架构原则：
- 依赖基础设施层的TimeSeriesCalculator
- 只包含业务逻辑，不包含算法实现
- 参数配置化，支持不同市场和策略
"""

import pandas as pd
from typing import Tuple, Dict, Any

from infrastructure.timeseries_calculator import TimeSeriesCalculator


# 市场参数配置（业务概念）
MARKET_PARAMS = {
    'CN': {  # A股市场参数（日线级别）
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},  # 统一国际标准
        'rsi': {'period': 6},  # A股更适合短周期
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
        'stochastic': {'period': 9, 'smooth': 3},  # 调整为9
        'vwap': {'reset': 'D', 'use_typical_price': True},  # A股T+1特色，使用pandas频率别D
        'cci': {'period': 14, 'constant': 0.015},  # 国内常用14周期
    },
    'CN_SHORT': {  # A股短线参数
        'macd': {'fast': 6, 'slow': 13, 'signal': 5},
        'rsi': {'period': 6},
        'bollinger': {'period': 10, 'std': 1.5},
        'atr': {'period': 7},
        'stochastic': {'period': 5, 'smooth': 3},
        'vwap': {'reset': 'D', 'use_typical_price': True},
        'cci': {'period': 10, 'constant': 0.015},
    },
    'US': {  # 美股市场参数
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'rsi': {'period': 14},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
        'stochastic': {'period': 14, 'smooth': 3},
        'vwap': {'reset': 'D', 'use_typical_price': True},
        'cci': {'period': 20, 'constant': 0.015},
    }
}

# 时间周期参数配置
TIME_FRAME_PARAMS = {
    '1min': {  # 1分钟级（高频交易）
        'rsi': {'period': 4},
        'macd': {'fast': 3, 'slow': 8, 'signal': 3},
        'bollinger': {'period': 10, 'std': 1.5},
        'atr': {'period': 7},
    },
    '5min': {  # 5分钟级
        'rsi': {'period': 6},
        'macd': {'fast': 5, 'slow': 13, 'signal': 5},
        'bollinger': {'period': 15, 'std': 1.8},
        'atr': {'period': 10},
    },
    '15min': {  # 15分钟级
        'rsi': {'period': 8},
        'macd': {'fast': 8, 'slow': 17, 'signal': 6},
        'bollinger': {'period': 18, 'std': 2.0},
        'atr': {'period': 12},
    },
    '30min': {  # 30分钟级
        'rsi': {'period': 10},
        'macd': {'fast': 10, 'slow': 21, 'signal': 7},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
    '60min': {  # 60分钟级
        'rsi': {'period': 12},
        'macd': {'fast': 12, 'slow': 24, 'signal': 8},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
    'daily': {  # 日线级（趋势交易）
        'rsi': {'period': 14},
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
    'weekly': {  # 周线级
        'rsi': {'period': 20},
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
}

# 指标分组（用于批量计算）
BASIC_INDICATORS = ['macd', 'rsi', 'bollinger']  # 基础组（高频使用）
STANDARD_INDICATORS = BASIC_INDICATORS + ['atr', 'kdj', 'obv']  # 标准组（一般策略）
ADVANCED_INDICATORS = STANDARD_INDICATORS + ['adx', 'vwap', 'cci']  # 高级组（复杂策略）


class TechnicalIndicators:
    """
    技术指标业务层
    
    将基础设施层的通用算法映射为量化交易领域的具体指标
    """
    
    def __init__(self, market: str = 'CN', timeframe: str = 'daily'):
        """
        Args:
            market: 市场类型 'CN'(A股), 'CN_SHORT'(A股短线), 'US'(美股)
            timeframe: 时间周期 '1min', '5min', '15min', '30min', '60min', 'daily', 'weekly'
        """
        self.market = market
        self.timeframe = timeframe
        self.params = self._merge_params(market, timeframe)
        self.calculator = TimeSeriesCalculator
    
    def _merge_params(self, market: str, timeframe: str) -> Dict[str, Any]:
        """
        合并市场参数和时间周期参数
        
        优先级：时间周期参数 > 市场参数
        注意：如果时间周期是'daily'，则直接使用市场参数，不进行覆盖
        """
        # 获取市场基础参数
        import copy
        base_params = copy.deepcopy(MARKET_PARAMS.get(market, MARKET_PARAMS['CN']))
        
        # 只在非daily时间周期时才进行覆盖
        if timeframe != 'daily' and timeframe in TIME_FRAME_PARAMS:
            timeframe_params = TIME_FRAME_PARAMS[timeframe]
            for indicator, params in timeframe_params.items():
                if indicator in base_params:
                    base_params[indicator].update(params)
        
        return base_params
    
    def calculate_macd(self, 
                      prices: pd.Series,
                      fast: int = None,
                      slow: int = None,
                      signal_period: int = None,  # 🔧 重命名避免与返回值冲突
                      use_china_standard: bool = True) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算MACD指标（Moving Average Convergence Divergence）
        
        业务含义：
        - 趋势跟踪动量指标
        - DIFF穿越DEA产生买卖信号
        - MACD柱状图表示两线差值
        
        命名体系：
        - 中国标准：DIFF（快慢线差）、DEA（信号线）、MACD柱（差值×2）
        - 国际标准：MACD、Signal、Histogram（无放大）
        
        Args:
            prices: 价格序列
            fast: 快线周期（默认使用市场参数）
            slow: 慢线周期（默认使用市场参数）
            signal_period: 信号线周期（默认使用市场参数）
            use_china_standard: 是否使用中国标准（柱状图×2）
        
        Returns:
            (DIFF, DEA, MACD柱) - 中国标准
            或 (MACD, Signal, Histogram) - 国际标准
        """
        params = self.params['macd']
        fast = fast or params['fast']
        slow = slow or params['slow']
        signal_period = signal_period or params['signal']  # 🔧 使用重命名后的参数
        
        # 中国市场习惯：柱状图放大2倍
        histogram_multiplier = 2.0 if use_china_standard else 1.0
        
        return self.calculator.calculate_dual_ema_oscillator(
            prices, fast, slow, signal_period, histogram_multiplier  # 🔧 传入正确的参数
        )
    
    def calculate_rsi(self, 
                     prices: pd.Series,
                     period: int = None) -> pd.Series:
        """
        计算RSI指标（Relative Strength Index）
        
        业务含义：
        - 相对强弱指标，范围0-100
        - RSI > 70 表示超买（可能回调）
        - RSI < 30 表示超卖（可能反弹）
        
        Args:
            prices: 价格序列
            period: 周期（默认使用市场参数）
        
        Returns:
            RSI值序列（0-100）
        """
        period = period or self.params['rsi']['period']
        return self.calculator.calculate_momentum_index(prices, period)
    
    def calculate_bollinger_bands(self,
                                  prices: pd.Series,
                                  period: int = None,
                                  std_multiplier: float = None) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算布林带（Bollinger Bands）
        
        业务含义：
        - 价格波动通道
        - 价格触及上轨可能超买
        - 价格触及下轨可能超卖
        - 通道收窄预示波动率降低
        
        Args:
            prices: 价格序列
            period: 周期（默认使用市场参数）
            std_multiplier: 标准差倍数（默认使用市场参数）
        
        Returns:
            (upper_band, middle_band, lower_band)
        """
        params = self.params['bollinger']
        period = period or params['period']
        std_multiplier = std_multiplier or params['std']
        
        return self.calculator.calculate_volatility_bands(
            prices, period, std_multiplier
        )
    
    def calculate_atr(self,
                     high: pd.Series,
                     low: pd.Series,
                     close: pd.Series,
                     period: int = None) -> pd.Series:
        """
        计算ATR指标（Average True Range）
        
        业务含义：
        - 平均真实波动幅度
        - 用于设置止损位
        - 用于仓位管理（波动越大仓位越小）
        
        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            period: 周期（默认使用市场参数）
        
        Returns:
            ATR值序列
        """
        period = period or self.params['atr']['period']
        previous_close = close.shift()
        
        return self.calculator.calculate_true_range_average(
            high, low, previous_close, period
        )
    
    def calculate_kdj(self,
                     high: pd.Series,
                     low: pd.Series,
                     close: pd.Series,
                     period: int = None,
                     smooth: int = None) -> Tuple[pd.Series, pd.Series]:
        """
        计算KDJ指标（Stochastic Oscillator）
        
        业务含义：
        - 随机指标，反映价格在区间中的相对位置
        - K值 > 80 超买，< 20 超卖
        - D值是K值的平滑
        - K线穿越D线产生信号
        
        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            period: 周期（默认使用市场参数）
            smooth: 平滑周期（默认使用市场参数）
        
        Returns:
            (k_line, d_line)
        """
        params = self.params['stochastic']
        period = period or params['period']
        smooth = smooth or params['smooth']
        
        return self.calculator.calculate_range_position(
            high, low, close, period, smooth
        )
    
    def calculate_obv(self,
                     close: pd.Series,
                     volume: pd.Series) -> pd.Series:
        """
        计算OBV指标（On-Balance Volume）
        
        业务含义：
        - 能量潮指标
        - 价格上涨累加成交量，下跌累减
        - 确认价格趋势的有效性
        
        Args:
            close: 收盘价序列
            volume: 成交量序列
        
        Returns:
            OBV值序列
        """
        return self.calculator.calculate_directional_volume(close, volume)
    
    def calculate_adx(self,
                     high: pd.Series,
                     low: pd.Series,
                     close: pd.Series,
                     period: int = None) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算ADX指标（Average Directional Index）
        
        业务含义：
        - 平均趋向指数，衡量趋势强度
        - +DI > -DI 表示上升趋势
        - +DI < -DI 表示下降趋势
        - ADX > 25 表示强趋势，< 20 表示无趋势
        
        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            period: 周期（默认14）
        
        Returns:
            (+DI, -DI, ADX)
        """
        period = period or 14
        return self.calculator.calculate_directional_indicators(
            high, low, close, period
        )
    
    def calculate_vwap(self,
                      high: pd.Series,
                      low: pd.Series,
                      close: pd.Series,
                      volume: pd.Series) -> pd.Series:
        """
        计算VWAP指标（Volume Weighted Average Price）
        
        业务含义：
        - 成交量加权平均价，机构常用
        - 价格高于VWAP表示相对强势
        - 价格低于VWAP表示相对弱势
        - A股特色：每日重置（T+1制度）
        
        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            volume: 成交量序列
        
        Returns:
            VWAP值序列
        """
        params = self.params.get('vwap', {'reset': 'daily', 'use_typical_price': True})
        
        # 计算典型价格
        if params['use_typical_price']:
            typical_price = (high + low + close) / 3
        else:
            typical_price = close
        
        return self.calculator.calculate_vwap(
            typical_price, volume, reset_period=params['reset']
        )
    
    def calculate_cci(self,
                     high: pd.Series,
                     low: pd.Series,
                     close: pd.Series,
                     period: int = None,
                     constant: float = None) -> pd.Series:
        """
        计算CCI指标（Commodity Channel Index）
        
        业务含义：
        - 商品通道指数，识别超买超卖
        - CCI > 100 表示超买
        - CCI < -100 表示超卖
        - 在[-100, 100]区间为正常波动
        
        Args:
            high: 最高价序列
            low: 最低价序列
            close: 收盘价序列
            period: 周期（默认使用市场参数）
            constant: 常数因子（默认0.015）
        
        Returns:
            CCI值序列
        """
        params = self.params.get('cci', {'period': 14, 'constant': 0.015})
        period = period or params['period']
        constant = constant or params['constant']
        
        return self.calculator.calculate_commodity_channel_index(
            high, low, close, period, constant
        )
    
    # 便捷方法：分层批量计算
    def calculate_all_indicators(self, 
                                data: pd.DataFrame,
                                indicator_set: str = 'standard') -> Dict[str, Any]:
        """
        分层批量计算指标
        
        Args:
            data: OHLCV数据，包含列['open', 'high', 'low', 'close', 'volume']
            indicator_set: 指标集合
                'basic'    - 基础指标（MACD, RSI, Bollinger）
                'standard' - 标准指标（+ATR, KDJ, OBV）
                'advanced' - 高级指标（+ADX, VWAP, CCI）
                'all'      - 所有指标
        
        Returns:
            包含指标的字典
        """
        results = {}
        
        # 基础指标（必算）
        results.update(self._calculate_basic_indicators(data))
        
        if indicator_set in ['standard', 'advanced', 'all']:
            results.update(self._calculate_standard_indicators(data))
        
        if indicator_set in ['advanced', 'all']:
            results.update(self._calculate_advanced_indicators(data))
        
        return results
    
    def _calculate_basic_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """计算基础指标组（高频使用）"""
        results = {}
        
        # MACD
        macd, signal, hist = self.calculate_macd(data['close'])
        results['macd'] = macd
        results['macd_signal'] = signal
        results['macd_hist'] = hist
        
        # RSI
        results['rsi'] = self.calculate_rsi(data['close'])
        
        # Bollinger Bands
        upper, middle, lower = self.calculate_bollinger_bands(data['close'])
        results['bb_upper'] = upper
        results['bb_middle'] = middle
        results['bb_lower'] = lower
        
        return results
    
    def _calculate_standard_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """计算标准指标组（一般策略）"""
        results = {}
        
        # ATR
        results['atr'] = self.calculate_atr(
            data['high'], data['low'], data['close']
        )
        
        # KDJ
        k, d = self.calculate_kdj(
            data['high'], data['low'], data['close']
        )
        results['kdj_k'] = k
        results['kdj_d'] = d
        
        # OBV
        if 'volume' in data.columns:
            results['obv'] = self.calculate_obv(
                data['close'], data['volume']
            )
        
        return results
    
    def _calculate_advanced_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """计算高级指标组（复杂策略）"""
        results = {}
        
        # ADX
        plus_di, minus_di, adx = self.calculate_adx(
            data['high'], data['low'], data['close']
        )
        results['adx_plus'] = plus_di
        results['adx_minus'] = minus_di
        results['adx'] = adx
        
        # VWAP
        if 'volume' in data.columns:
            results['vwap'] = self.calculate_vwap(
                data['high'], data['low'], data['close'], data['volume']
            )
        
        # CCI
        results['cci'] = self.calculate_cci(
            data['high'], data['low'], data['close']
        )
        
        return results
