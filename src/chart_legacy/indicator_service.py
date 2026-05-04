"""技术指标业务层封装

从 market_chart/markets/src/core/signal/indicator_service.py 整包移植
仅调整导入路径，保持原始逻辑不变。
"""

import copy
import pandas as pd
from typing import Tuple, Dict, Any

from src.chart_legacy.timeseries_calculator import TimeSeriesCalculator


MARKET_PARAMS = {
    'CN': {
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'rsi': {'period': 6},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
        'stochastic': {'period': 9, 'smooth': 3},
        'vwap': {'reset': 'D', 'use_typical_price': True},
        'cci': {'period': 14, 'constant': 0.015},
    },
    'CN_SHORT': {
        'macd': {'fast': 6, 'slow': 13, 'signal': 5},
        'rsi': {'period': 6},
        'bollinger': {'period': 10, 'std': 1.5},
        'atr': {'period': 7},
        'stochastic': {'period': 5, 'smooth': 3},
        'vwap': {'reset': 'D', 'use_typical_price': True},
        'cci': {'period': 10, 'constant': 0.015},
    },
    'US': {
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'rsi': {'period': 14},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
        'stochastic': {'period': 14, 'smooth': 3},
        'vwap': {'reset': 'D', 'use_typical_price': True},
        'cci': {'period': 20, 'constant': 0.015},
    },
}

TIME_FRAME_PARAMS = {
    '1min': {
        'rsi': {'period': 4},
        'macd': {'fast': 3, 'slow': 8, 'signal': 3},
        'bollinger': {'period': 10, 'std': 1.5},
        'atr': {'period': 7},
    },
    '5min': {
        'rsi': {'period': 6},
        'macd': {'fast': 5, 'slow': 13, 'signal': 5},
        'bollinger': {'period': 15, 'std': 1.8},
        'atr': {'period': 10},
    },
    '15min': {
        'rsi': {'period': 8},
        'macd': {'fast': 8, 'slow': 17, 'signal': 6},
        'bollinger': {'period': 18, 'std': 2.0},
        'atr': {'period': 12},
    },
    '30min': {
        'rsi': {'period': 10},
        'macd': {'fast': 10, 'slow': 21, 'signal': 7},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
    '60min': {
        'rsi': {'period': 12},
        'macd': {'fast': 12, 'slow': 24, 'signal': 8},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
    'daily': {
        'rsi': {'period': 14},
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
    'weekly': {
        'rsi': {'period': 20},
        'macd': {'fast': 12, 'slow': 26, 'signal': 9},
        'bollinger': {'period': 20, 'std': 2.0},
        'atr': {'period': 14},
    },
}


class TechnicalIndicators:
    """技术指标业务层"""

    def __init__(self, market: str = 'CN', timeframe: str = 'daily'):
        self.market = market
        self.timeframe = timeframe
        self.params = self._merge_params(market, timeframe)
        self.calculator = TimeSeriesCalculator

    def _merge_params(self, market: str, timeframe: str) -> Dict[str, Any]:
        base_params = copy.deepcopy(MARKET_PARAMS.get(market, MARKET_PARAMS['CN']))
        if timeframe != 'daily' and timeframe in TIME_FRAME_PARAMS:
            timeframe_params = TIME_FRAME_PARAMS[timeframe]
            for indicator, params in timeframe_params.items():
                if indicator in base_params:
                    base_params[indicator].update(params)
        return base_params

    def calculate_macd(
        self,
        prices: pd.Series,
        fast: int = None,
        slow: int = None,
        signal_period: int = None,
        use_china_standard: bool = True,
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        params = self.params['macd']
        fast = fast or params['fast']
        slow = slow or params['slow']
        signal_period = signal_period or params['signal']
        histogram_multiplier = 2.0 if use_china_standard else 1.0
        return self.calculator.calculate_dual_ema_oscillator(
            prices, fast, slow, signal_period, histogram_multiplier
        )

    def calculate_rsi(self, prices: pd.Series, period: int = None) -> pd.Series:
        period = period or self.params['rsi']['period']
        return self.calculator.calculate_momentum_index(prices, period)

    def calculate_bollinger_bands(
        self,
        prices: pd.Series,
        period: int = None,
        std_multiplier: float = None,
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        params = self.params['bollinger']
        period = period or params['period']
        std_multiplier = std_multiplier or params['std']
        return self.calculator.calculate_volatility_bands(
            prices, period, std_multiplier
        )

    def calculate_atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = None,
    ) -> pd.Series:
        period = period or self.params['atr']['period']
        previous_close = close.shift()
        return self.calculator.calculate_true_range_average(
            high, low, previous_close, period
        )

    def calculate_kdj(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = None,
        smooth: int = None,
    ) -> Tuple[pd.Series, pd.Series]:
        params = self.params['stochastic']
        period = period or params['period']
        smooth = smooth or params['smooth']
        return self.calculator.calculate_range_position(
            high, low, close, period, smooth
        )

    def calculate_obv(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        return self.calculator.calculate_directional_volume(close, volume)

    def calculate_adx(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = None,
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        period = period or 14
        return self.calculator.calculate_directional_indicators(
            high, low, close, period
        )

    def calculate_vwap(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
    ) -> pd.Series:
        params = self.params.get('vwap', {'reset': 'daily', 'use_typical_price': True})
        if params['use_typical_price']:
            typical_price = (high + low + close) / 3
        else:
            typical_price = close
        return self.calculator.calculate_vwap(
            typical_price, volume, reset_period=params['reset']
        )

    def calculate_cci(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = None,
        constant: float = None,
    ) -> pd.Series:
        params = self.params.get('cci', {'period': 14, 'constant': 0.015})
        period = period or params['period']
        constant = constant or params['constant']
        return self.calculator.calculate_commodity_channel_index(
            high, low, close, period, constant
        )
