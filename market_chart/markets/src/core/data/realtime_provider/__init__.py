"""
实时数据提供者体系

三个独立职责：
- RealtimeKlineProvider: 日/周/月实时K线
- IntradayProvider: 分时数据（交易时段感知）
- OrderBookProvider: 盘口数据（5档买卖盘）
"""

from .interface import IQuoteFetcher, ITradingCalendar
from .types import (
    RealtimeKline,
    OrderBookSnapshot,
    IntradayCache,
)
from .realtime_kline_provider import RealtimeKlineProvider
from .intraday_provider import IntradayProvider
from .orderbook_provider import OrderBookProvider

__all__ = [
    # Protocols
    "IQuoteFetcher",
    "ITradingCalendar",
    # Types
    "RealtimeKline",
    "OrderBookSnapshot",
    "IntradayCache",
    # Providers
    "RealtimeKlineProvider",
    "IntradayProvider",
    "OrderBookProvider",
]
