"""时序数据统计计算 - 基础设施层

从 temp/markets/src/infrastructure/timeseries_calculator.py 整包移植
保持原始逻辑不变。
"""

import logging
import warnings
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger('chart_legacy.TimeSeriesCalculator')


class TimeSeriesCalculator:
    """通用技术指标计算器"""

    @staticmethod
    def safe_divide(
        numerator: pd.Series, denominator: pd.Series, default: float = np.nan
    ) -> pd.Series:
        result = numerator / denominator
        result = result.replace([np.inf, -np.inf], default)
        return result

    @staticmethod
    def validate_input(
        prices: pd.Series, min_length: int, name: str = 'prices'
    ) -> None:
        if prices is None or len(prices) == 0:
            raise ValueError(f"{name} 不能为空")
        if len(prices) < min_length:
            warnings.warn(
                f"{name} 长度({len(prices)})小于推荐最小值({min_length})，"
                f"前{min_length - 1}个结果将为NaN"
            )

    @staticmethod
    def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
        return prices.rolling(window=period).mean()

    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
        return prices.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_dual_ema_oscillator(
        values: pd.Series,
        fast_period: int,
        slow_period: int,
        signal_period: int,
        histogram_multiplier: float = 1.0,
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = TimeSeriesCalculator.calculate_ema(values, fast_period)
        ema_slow = TimeSeriesCalculator.calculate_ema(values, slow_period)
        main_line = ema_fast - ema_slow
        signal_line = main_line.ewm(span=signal_period, adjust=False).mean()
        histogram = (main_line - signal_line) * histogram_multiplier
        return main_line, signal_line, histogram

    @staticmethod
    def calculate_momentum_index(values: pd.Series, period: int) -> pd.Series:
        delta = values.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        index = 100 - (100 / (1 + rs))
        index = index.clip(0, 100)
        return index

    @staticmethod
    def calculate_volatility_bands(
        values: pd.Series, period: int, std_multiplier: float
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        middle = values.rolling(window=period).mean()
        std = values.rolling(window=period).std()
        upper = middle + (std_multiplier * std)
        lower = middle - (std_multiplier * std)
        return upper, middle, lower

    @staticmethod
    def calculate_true_range_average(
        high: pd.Series,
        low: pd.Series,
        previous_close: pd.Series,
        period: int,
    ) -> pd.Series:
        tr1 = high - low
        tr2 = abs(high - previous_close)
        tr3 = abs(low - previous_close)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    @staticmethod
    def calculate_range_position(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int,
        smooth_period: int = 3,
    ) -> Tuple[pd.Series, pd.Series]:
        lowest = low.rolling(window=period).min()
        highest = high.rolling(window=period).max()
        position = 100 * (close - lowest) / (highest - lowest)
        smooth_position = position.rolling(window=smooth_period).mean()
        return position, smooth_position

    @staticmethod
    def calculate_directional_volume(
        close: pd.Series, volume: pd.Series
    ) -> pd.Series:
        directional = (np.sign(close.diff()) * volume).fillna(0)
        cumulative = directional.cumsum()
        return cumulative

    @staticmethod
    def calculate_directional_indicators(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0),
            index=high.index,
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0),
            index=high.index,
        )
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        smoothed_tr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        smoothed_plus_dm = plus_dm.ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean()
        smoothed_minus_dm = minus_dm.ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean()
        plus_di = 100 * smoothed_plus_dm / smoothed_tr.replace(0, np.nan)
        minus_di = 100 * smoothed_minus_dm / smoothed_tr.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        return plus_di, minus_di, adx

    @staticmethod
    def calculate_vwap(
        typical_price: pd.Series,
        volume: pd.Series,
        reset_period: str = 'D',
    ) -> pd.Series:
        price_volume = typical_price * volume
        if reset_period and isinstance(typical_price.index, pd.DatetimeIndex):
            pv_cumsum = price_volume.groupby(pd.Grouper(freq=reset_period)).cumsum()
            vol_cumsum = volume.groupby(pd.Grouper(freq=reset_period)).cumsum()
        else:
            pv_cumsum = price_volume.cumsum()
            vol_cumsum = volume.cumsum()
        vwap = pv_cumsum / vol_cumsum.replace(0, np.nan)
        return vwap

    @staticmethod
    def calculate_commodity_channel_index(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int,
        constant: float = 0.015,
    ) -> pd.Series:
        typical_price = (high + low + close) / 3
        sma = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
        )
        cci = (typical_price - sma) / (constant * mad.replace(0, np.nan))
        return cci
