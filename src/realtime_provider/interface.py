"""
实时数据提供者接口

定义 IQuoteFetcher + ITradingCalendar Protocol，
为 realtime_provider 体系提供统一的依赖注入契约。
"""

from typing import Optional, Protocol, runtime_checkable

import pandas as pd

from src.chart_legacy.market_types import (
    IntradayTickRecord,
    OrderBookLevel,
    TradeDetailRecord,
)
from src.chart_legacy.market_enums import TradingPhase


@runtime_checkable
class IQuoteFetcher(Protocol):
    """实时行情获取器 — 统一接口封装底层数据源

    当前实现:
    - DataFetcherManager (src/data_provider/fetcher_manager.py)
    - 未来可扩展其他实时行情源
    """

    def get_realtime_quote(self, symbol: str) -> Optional["UnifiedRealtimeQuote"]:
        """获取实时行情快照

        Returns:
            UnifiedRealtimeQuote: open_price, high, low, price, volume, turnover_rate
            None: 获取失败或无可用的行情源
        """
        ...

    def get_intraday_ticks(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取当日分时tick数据（1分钟级别）

        Returns:
            DataFrame columns: time, price, volume, avg_price
            None: 获取失败
        """
        ...

    def get_order_book(
        self, symbol: str
    ) -> Optional[tuple[list[OrderBookLevel], list[OrderBookLevel]]]:
        """获取盘口数据

        Returns:
            (bids, asks) — bids从高到低排序，asks从低到高排序
            None: 获取失败
        """
        ...

    def get_trade_records(self, symbol: str) -> Optional[list[TradeDetailRecord]]:
        """获取逐笔成交记录

        Returns:
            TradeDetailRecord 列表，按时间倒序
            None: 获取失败
        """
        ...


@runtime_checkable
class ITradingCalendar(Protocol):
    """交易时段判断 — 由 MarketTimeUtils 封装"""

    def determine_trading_phase(
        self, symbol: str, local_time: pd.Timestamp
    ) -> TradingPhase:
        """判断当前交易时段"""
        ...

    def is_trading_day(self, symbol: str, date: pd.Timestamp) -> bool:
        """判断是否为交易日"""
        ...

    def trading_days_between(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        """获取[start, end]内的所有交易日"""
        ...

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        """获取下一个交易日"""
        ...
