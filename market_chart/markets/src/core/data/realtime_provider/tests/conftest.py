"""
realtime_provider 测试共享 fixtures

Mock 策略：
- IQuoteFetcher: 用 MagicMock 模拟，按测试需要设置返回值
- ITradingCalendar: 用 MagicMock 模拟交易时段判断
- IDataProvider: 用 MagicMock 模拟历史数据获取
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.data.providers.protocols import IntradayData, IntradayTickRecord, OrderBookLevel, TradeDetailRecord
from core.share.market.market_enums import TradingPhase


# ------------------------------------------------------------------ #
# Mock 行情数据
# ------------------------------------------------------------------ #
@dataclass
class MockQuote:
    """模拟实时行情"""
    symbol: str = "600519"
    name: str = "贵州茅台"
    price: float = 1800.0
    open_price: float = 1790.0
    high: float = 1810.0
    low: float = 1785.0
    pre_close: float = 1788.0
    volume: int = 100000
    turnover_rate: float = 0.5


@pytest.fixture
def mock_quote():
    return MockQuote()


# ------------------------------------------------------------------ #
# Mock IQuoteFetcher
# ------------------------------------------------------------------ #
@pytest.fixture
def mock_quote_fetcher(mock_quote):
    """模拟行情获取器 — 默认所有方法返回有效数据"""
    fetcher = MagicMock()

    # 实时行情
    fetcher.get_realtime_quote.return_value = mock_quote

    # 分时 tick — 返回 DataFrame
    fetcher.get_intraday_ticks.return_value = pd.DataFrame({
        "time": ["09:30", "09:31", "09:32"],
        "price": [1800.0, 1801.0, 1802.0],
        "volume": [100, 200, 300],
        "avg_price": [1800.0, 1800.5, 1801.0],
    })

    # 盘口 — 返回 (bids, asks)
    fetcher.get_order_book.return_value = (
        [OrderBookLevel(price=1799.0, volume=100), OrderBookLevel(price=1798.0, volume=200)],
        [OrderBookLevel(price=1801.0, volume=150), OrderBookLevel(price=1802.0, volume=250)],
    )

    # 成交明细
    fetcher.get_trade_records.return_value = [
        TradeDetailRecord(time="09:30", price=1800.0, volume=100, direction="B"),
        TradeDetailRecord(time="09:31", price=1801.0, volume=200, direction="S"),
    ]

    return fetcher


@pytest.fixture
def mock_quote_fetcher_fail():
    """模拟行情获取器 — 所有方法返回 None"""
    fetcher = MagicMock()
    fetcher.get_realtime_quote.return_value = None
    fetcher.get_intraday_ticks.return_value = None
    fetcher.get_order_book.return_value = None
    fetcher.get_trade_records.return_value = None
    return fetcher


# ------------------------------------------------------------------ #
# Mock ITradingCalendar
# ------------------------------------------------------------------ #
@pytest.fixture
def mock_calendar_trading():
    """模拟日历 — 当前为交易中"""
    calendar = MagicMock()
    calendar.determine_trading_phase.return_value = TradingPhase.TRADING
    calendar.is_trading_day.return_value = True
    calendar.trading_days_between.return_value = pd.date_range("2026-05-12", "2026-05-14")
    calendar.next_trading_day.side_effect = lambda d: d + pd.Timedelta(days=1)
    return calendar


@pytest.fixture
def mock_calendar_before_open():
    """模拟日历 — 当前为盘前"""
    calendar = MagicMock()
    calendar.determine_trading_phase.return_value = TradingPhase.BEFORE_OPEN
    return calendar


@pytest.fixture
def mock_calendar_after_close():
    """模拟日历 — 当前为盘后"""
    calendar = MagicMock()
    calendar.determine_trading_phase.return_value = TradingPhase.AFTER_CLOSE
    return calendar


@pytest.fixture
def mock_calendar_noon_break():
    """模拟日历 — 当前为午休"""
    calendar = MagicMock()
    calendar.determine_trading_phase.return_value = TradingPhase.NOON_BREAK
    return calendar


# ------------------------------------------------------------------ #
# Mock IDataProvider (历史数据)
# ------------------------------------------------------------------ #
@pytest.fixture
def mock_history_provider():
    """模拟历史数据提供者 — 返回本周/本月日线"""
    provider = MagicMock()

    # 默认返回3天日线
    provider.fetch.return_value = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-05-12", "2026-05-13", "2026-05-14"]),
        "open": [1780.0, 1788.0, 1790.0],
        "high": [1795.0, 1800.0, 1810.0],
        "low": [1775.0, 1780.0, 1785.0],
        "close": [1788.0, 1795.0, 1800.0],
        "volume": [50000, 60000, 70000],
    })

    return provider


@pytest.fixture
def mock_history_provider_empty():
    """模拟历史数据提供者 — 返回空数据"""
    provider = MagicMock()
    provider.fetch.return_value = None
    return provider


# ------------------------------------------------------------------ #
# Mock BarAggregator
# ------------------------------------------------------------------ #
@pytest.fixture
def mock_bar_aggregator():
    """模拟 K线聚合器"""
    aggregator = MagicMock()

    # 周线聚合
    aggregator.daily_to_weekly.return_value = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-05-12"]),
        "open": [1780.0],
        "high": [1810.0],
        "low": [1775.0],
        "close": [1800.0],
        "volume": [180000],
    })

    # 月线聚合
    aggregator.daily_to_monthly.return_value = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-05-01"]),
        "open": [1700.0],
        "high": [1810.0],
        "low": [1650.0],
        "close": [1800.0],
        "volume": [5000000],
    })

    return aggregator


# ------------------------------------------------------------------ #
# Mock OrderBookProvider
# ------------------------------------------------------------------ #
@pytest.fixture
def mock_orderbook_provider():
    """模拟盘口提供者"""
    from ..orderbook_provider import OrderBookProvider
    provider = MagicMock(spec=OrderBookProvider)
    provider.get_order_book.return_value = MagicMock(
        bids=[OrderBookLevel(price=1799.0, volume=100)],
        asks=[OrderBookLevel(price=1801.0, volume=150)],
    )
    provider.get_trade_records.return_value = [
        {"time": "09:30", "price": 1800.0, "volume": 100, "type": "B"},
    ]
    return provider


# ------------------------------------------------------------------ #
# 辅助数据构建
# ------------------------------------------------------------------ #
@pytest.fixture
def sample_intraday_data():
    """构建一个 IntradayData 样本"""
    return IntradayData(
        symbol="600519",
        name="贵州茅台",
        current_price=1800.0,
        yesterday_close=1788.0,
        change=12.0,
        change_percent=0.67,
        ticks=[
            IntradayTickRecord(time="09:30", price=1800.0, volume=100, avg_price=1800.0),
            IntradayTickRecord(time="09:31", price=1801.0, volume=200, avg_price=1800.5),
        ],
        order_book_bids=[OrderBookLevel(price=1799.0, volume=100)],
        order_book_asks=[OrderBookLevel(price=1801.0, volume=150)],
        trade_records=[TradeDetailRecord(time="09:30", price=1800.0, volume=100, direction="B")],
        trade_date=pd.Timestamp("2026-05-14"),
        order_book_message="",
        trade_records_message="",
        is_index=False,
        should_poll=True,
    )
