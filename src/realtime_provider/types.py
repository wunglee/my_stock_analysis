"""
实时数据类型定义

定义 RealtimeKline, OrderBookSnapshot, IntradayCache 等DTO，
为 realtime_provider 提供统一的数据结构。
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.chart_legacy.market_types import (
    IntradayData,
    IntradayTickRecord,
    OrderBookLevel,
    TradeDetailRecord,
)


@dataclass
class RealtimeKline:
    """实时K线数据 — 单条K柱 + 交易状态

    兼容前端 chart 组件的数据需求。
    """
    date: str                    # 交易日期 YYYY-MM-DD
    open: float | None           # 开盘价
    high: float | None           # 最高价
    low: float | None            # 最低价
    close: float | None          # 收盘价（最新价）
    volume: int                  # 成交量
    turnover_rate: float | None  # 换手率
    trading_phase: str           # 交易时段描述
    should_poll: bool            # 是否应继续轮询

    def to_dict(self) -> dict[str, Any]:
        """转换为前端兼容的 dict"""
        return {
            'date': self.date,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'turnover_rate': self.turnover_rate,
            'trading_phase': self.trading_phase,
            'should_poll': self.should_poll,
        }

    @classmethod
    def from_quote(
        cls,
        quote: "UnifiedRealtimeQuote",
        trade_date: str,
        trading_phase: str,
        should_poll: bool,
    ) -> "RealtimeKline":
        """从实时行情创建 RealtimeKline"""
        return cls(
            date=trade_date,
            open=quote.open_price if hasattr(quote, 'open_price') else None,
            high=quote.high if hasattr(quote, 'high') else None,
            low=quote.low if hasattr(quote, 'low') else None,
            close=quote.price if hasattr(quote, 'price') else None,
            volume=getattr(quote, 'volume', 0) or 0,
            turnover_rate=getattr(quote, 'turnover_rate', None),
            trading_phase=trading_phase,
            should_poll=should_poll,
        )

    @classmethod
    def empty(
        cls,
        trade_date: str,
        trading_phase: str,
        should_poll: bool,
    ) -> "RealtimeKline":
        """创建空K线（无实时行情时）"""
        return cls(
            date=trade_date,
            open=None,
            high=None,
            low=None,
            close=None,
            volume=0,
            turnover_rate=None,
            trading_phase=trading_phase,
            should_poll=should_poll,
        )


@dataclass
class OrderBookSnapshot:
    """盘口快照"""
    bids: list[OrderBookLevel]  # 买盘，从高到低
    asks: list[OrderBookLevel]  # 卖盘，从低到高
    timestamp: pd.Timestamp | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为前端兼容的 dict"""
        return {
            'bids': [{'price': b.price, 'volume': b.volume} for b in self.bids],
            'asks': [{'price': a.price, 'volume': a.volume} for a in self.asks],
        }


@dataclass
class IntradayCache:
    """分时数据缓存 — 按 symbol 存储当日数据"""

    _data: dict[str, IntradayData] = field(default_factory=dict)

    def get(self, symbol: str) -> IntradayData | None:
        """获取缓存的分时数据"""
        return self._data.get(symbol)

    def set(self, symbol: str, data: IntradayData) -> None:
        """写入或更新分时数据"""
        self._data[symbol] = data

    def clear(self, symbol: str) -> None:
        """清除指定 symbol 的缓存"""
        self._data.pop(symbol, None)

    def clear_all(self) -> None:
        """清除所有缓存"""
        self._data.clear()
