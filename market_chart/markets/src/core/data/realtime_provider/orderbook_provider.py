"""
盘口数据提供者 — 5档买卖盘 + 逐笔成交

职责：
1. 获取实时5档买卖盘
2. 获取逐笔成交记录
3. 无交易时段判断 — 调用方（IntradayProvider）决定是否获取

设计：纯透传 IQuoteFetcher，无业务逻辑，便于测试和替换数据源。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .types import OrderBookSnapshot

if TYPE_CHECKING:
    from .interface import IQuoteFetcher

logger = logging.getLogger(__name__)


class OrderBookProvider:
    """盘口数据提供者"""

    def __init__(self, quote_fetcher: IQuoteFetcher) -> None:
        self._quote = quote_fetcher

    def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        """获取5档盘口

        Args:
            symbol: 股票代码

        Returns:
            OrderBookSnapshot: bids/asks
            None: 获取失败
        """
        try:
            result = self._quote.get_order_book(symbol)
            if result is None:
                return None
            bids, asks = result
            return OrderBookSnapshot(bids=bids, asks=asks)
        except Exception as e:
            logger.warning(f"[OrderBook] {symbol} 获取盘口异常: {e}")
            return None

    def get_trade_records(self, symbol: str) -> list[dict] | None:
        """获取逐笔成交记录

        Args:
            symbol: 股票代码

        Returns:
            dict 列表，每个元素包含: time, price, volume, type
            None: 获取失败
        """
        try:
            records = self._quote.get_trade_records(symbol)
            if records is None:
                return None
            return [
                {
                    "time": r.time,
                    "price": r.price,
                    "volume": r.volume,
                    "type": r.direction,
                }
                for r in records
            ]
        except Exception as e:
            logger.warning(f"[OrderBook] {symbol} 获取成交明细异常: {e}")
            return None
