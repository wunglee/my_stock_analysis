"""市场工具类（领域层共享）

职责：
- 提供市场识别、推断等基础功能
- 支持从 symbol 推断市场类型
- 可被所有层（应用层、领域层）复用
"""

import logging
from typing import Optional

import pandas as pd

from src.chart_legacy.market_enums import MarketCode

logger = logging.getLogger(__name__)


class MarketUtils:
    """市场工具类

    提供市场相关的通用工具方法
    """

    @staticmethod
    def infer_market_from_symbol(symbol: str) -> MarketCode:
        """从股票/指数代码推断市场类型

        Args:
            symbol: 股票/指数代码（如 '000300.SH', '^GSPC.US', 'HSI'）

        Returns:
            MarketCode: 推断出的市场代码枚举

        Examples:
            >>> MarketUtils.infer_market_from_symbol('000300.SH')
            <MarketCode.CN: 'CN'>
            >>> MarketUtils.infer_market_from_symbol('^GSPC.US')
            <MarketCode.US: 'US'>
            >>> MarketUtils.infer_market_from_symbol('HSI.HK')
            <MarketCode.HK: 'HK'>

        规则：
            - A股市场：.SH（上海）、.SZ（深圳）、.CN
            - 港股市场：.HK、.HKG、HSI（恒生指数）
            - 美股市场：.US（如 ^GSPC.US、^DJI.US、^IXIC.US）
            - 日本市场：.JP
            - 欧洲市场：.EU
            - 新加坡：.SG
            - 默认：MarketCode.CN
        """
        if not symbol:
            return MarketCode.CN

        symbol_upper = symbol.upper()

        # A股市场（上海/深圳）
        if any(symbol_upper.endswith(suffix) for suffix in ['.SH', '.SZ', '.CN']):
            return MarketCode.CN

        # 港股市场
        if any(symbol_upper.endswith(suffix) for suffix in ['.HK', '.HKG']) or symbol_upper == 'HSI':
            return MarketCode.HK

        # 日本市场
        if symbol_upper.endswith('.JP'):
            return MarketCode.JP

        # 欧洲市场
        if symbol_upper.endswith('.EU'):
            return MarketCode.EU

        # 新加坡市场
        if symbol_upper.endswith('.SG'):
            return MarketCode.SG

        # 美股市场（.US 后缀）
        if symbol_upper.endswith('.US'):
            return MarketCode.US

        # 默认为 A股市场
        return MarketCode.CN

    @staticmethod
    def is_index(symbol: str) -> bool:
        """判断是否为指数代码"""
        return symbol.startswith('^')
