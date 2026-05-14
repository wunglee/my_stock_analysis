"""
市场枚举定义（共享模块）

职责：定义标准化的市场代码枚举
用途：替换项目中所有字符串常量，提供类型安全和自动补全
"""

from enum import Enum
from typing import Any


class MarketCode(str, Enum):
    """
    市场代码枚举
    
    继承自str使其可直接用于字符串比较和字典键
    覆盖market_config.py中的所有市场
    """
    CN = 'CN'  # 中国A股
    US = 'US'  # 美国股市
    HK = 'HK'  # 香港股市
    JP = 'JP'  # 日本股市
    EU = 'EU'  # 欧洲股市
    SG = 'SG'  # 新加坡股市
    UNKNOWN = 'UNKNOWN'  # 未识别/默认市场
    
    @classmethod
    def parse(cls, code: Any) -> 'MarketCode':
        """集中解析市场代码（字符串/枚举），失败回退为 UNKNOWN
        
        Args:
            code: 市场代码（字符串或枚举）
        
        Returns:
            MarketCode: 解析后的枚举，无法识别时返回 UNKNOWN
        
        Examples:
            >>> MarketCode.parse('CN')
            <MarketCode.CN: 'CN'>
            >>> MarketCode.parse(MarketCode.US)
            <MarketCode.US: 'US'>
            >>> MarketCode.parse('invalid')
            <MarketCode.UNKNOWN: 'UNKNOWN'>
        """
        if isinstance(code, cls):
            return code
        if isinstance(code, str):
            code_upper = code.upper()
            if cls.is_valid(code_upper):
                return cls(code_upper)
        return cls.UNKNOWN
    
    @classmethod
    def get_all_codes(cls) -> list:
        """获取所有市场代码"""
        return [market.value for market in cls]
    
    @classmethod
    def is_valid(cls, code: str) -> bool:
        """验证市场代码是否有效"""
        return code in cls.get_all_codes()
    
    def __str__(self) -> str:
        """支持直接字符串转换"""
        return self.value


class DataSource(str, Enum):
    """
    数据源枚举
    
    统一管理所有支持的数据源
    """
    YAHOO = 'yahoo'              # Yahoo Finance（全球）
    JOINQUANT = 'joinquant'      # 聚宽（A股优先）
    WIND = 'wind'                # Wind金融终端（港股、A股）
    TUSHARE = 'tushare'          # Tushare（A股、港股）
    AKSHARE = 'akshare'          # AKShare（全市场，免费无限制）
    ALPHA_VANTAGE = 'alpha_vantage'  # Alpha Vantage（美股）
    IEX = 'iex'                  # IEX Cloud（美股）
    MOCK = 'mock'                # 模拟数据源（测试）
    
    @classmethod
    def get_all_sources(cls) -> list:
        """获取所有数据源"""
        return [source.value for source in cls]
    
    @classmethod
    def is_valid(cls, source: str) -> bool:
        """验证数据源是否有效"""
        return source in cls.get_all_sources()
    
    def __str__(self) -> str:
        """支持直接字符串转换"""
        return self.value


class TradingPhase(str, Enum):
    """
    交易时段枚举
    
    定义市场的不同交易阶段，用于控制数据返回逻辑
    """
    BEFORE_OPEN = 'before_open'  # 盘前集合竞价时段（09:00-09:30）
    TRADING = 'trading'          # 盘中交易时段（09:30-11:30 和 13:00-15:00）
    NOON_BREAK = 'noon_break'    # 午盘休市时段（11:30-13:00）
    AFTER_CLOSE = 'after_close'  # 盘后时段（15:00之后）
    
    @classmethod
    def parse(cls, phase: Any) -> 'TradingPhase':
        """解析交易时段
        
        Args:
            phase: 交易时段（字符串或枚举）
        
        Returns:
            TradingPhase: 解析后的枚举
        
        Raises:
            ValueError: 当传入无效的交易时段时
            TypeError: 当传入类型不正确时
        
        支持的值：
        - 'before_open': 集合竞价
        - 'trading': 交易时段（上午+下午）
        - 'noon_break': 午休
        - 'after_close': 盘后
        """
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
        """支持直接字符串转换"""
        return self.value

