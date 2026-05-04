"""市场枚举定义

从 market_chart/markets/src/core/share/market/market_enums.py 整包移植
保持原始逻辑不变。
"""

from enum import Enum
from typing import Any


class MarketCode(str, Enum):
    """市场代码枚举"""

    CN = 'CN'
    US = 'US'
    HK = 'HK'
    JP = 'JP'
    EU = 'EU'
    SG = 'SG'
    UNKNOWN = 'UNKNOWN'

    @classmethod
    def parse(cls, code: Any) -> 'MarketCode':
        if isinstance(code, cls):
            return code
        if isinstance(code, str):
            code_upper = code.upper()
            if cls.is_valid(code_upper):
                return cls(code_upper)
        return cls.UNKNOWN

    @classmethod
    def get_all_codes(cls) -> list:
        return [market.value for market in cls]

    @classmethod
    def is_valid(cls, code: str) -> bool:
        return code in cls.get_all_codes()

    def __str__(self) -> str:
        return self.value


class DataSource(str, Enum):
    """数据源枚举"""

    YAHOO = 'yahoo'
    JOINQUANT = 'joinquant'
    WIND = 'wind'
    TUSHARE = 'tushare'
    AKSHARE = 'akshare'
    ALPHA_VANTAGE = 'alpha_vantage'
    IEX = 'iex'
    MOCK = 'mock'

    @classmethod
    def get_all_sources(cls) -> list:
        return [source.value for source in cls]

    @classmethod
    def is_valid(cls, source: str) -> bool:
        return source in cls.get_all_sources()

    def __str__(self) -> str:
        return self.value


class TradingPhase(str, Enum):
    """交易时段枚举"""

    BEFORE_OPEN = 'before_open'
    TRADING = 'trading'
    NOON_BREAK = 'noon_break'
    AFTER_CLOSE = 'after_close'

    @classmethod
    def parse(cls, phase: Any) -> 'TradingPhase':
        if isinstance(phase, cls):
            return phase
        if isinstance(phase, str):
            try:
                return cls(phase.lower())
            except ValueError:
                valid_values = [p.value for p in cls]
                raise ValueError(
                    f"无效的交易时段: '{phase}'. "
                    f"支持的值为: {valid_values}"
                )
        raise TypeError(
            f"交易时段必须是 TradingPhase 枚举或字符串，当前类型: {type(phase)}"
        )

    def __str__(self) -> str:
        return self.value
