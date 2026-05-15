"""
IntradayProvider 单元测试

职责：交易时段感知的分时数据获取。
测试重点：
- 4 个交易时段的分支覆盖
- 缓存读写
- 前端数据结构兼容
- 异常兜底
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.data.providers.protocols import IntradayData, IntradayTickRecord, OrderBookLevel, TradeDetailRecord
from core.share.market.market_enums import TradingPhase

from ..intraday_provider import IntradayProvider


class TestIntradayProviderTradingPhase:
    """交易时段分派测试"""

    def test_before_open_no_cache(self, mock_quote_fetcher, mock_calendar_before_open):
        """盘前：无缓存 → 返回空数据 + should_poll=True"""
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_before_open)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["should_poll"] is True
        assert result["trading_phase"] == TradingPhase.BEFORE_OPEN.value
        assert result["times"] == []
        assert result["prices"] == []
        assert result["current_price"] == 0.0

    def test_before_open_with_cache(self, mock_quote_fetcher, mock_calendar_before_open, sample_intraday_data):
        """盘前：有缓存 → 返回缓存数据"""
        from ..types import IntradayCache
        cache = IntradayCache()
        cache.set("600519", sample_intraday_data)

        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_before_open, cache=cache)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["symbol"] == "600519"
        assert result["current_price"] == 1800.0
        assert result["should_poll"] is True
        assert result["trading_phase"] == TradingPhase.BEFORE_OPEN.value

    def test_trading_normal(self, mock_quote_fetcher, mock_calendar_trading, mock_orderbook_provider):
        """盘中：正常获取实时数据"""
        provider = IntradayProvider(
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            orderbook_provider=mock_orderbook_provider,
        )
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["should_poll"] is True
        assert result["trading_phase"] == TradingPhase.TRADING.value
        assert result["current_price"] == 1800.0
        assert result["yesterday_close"] == 1788.0
        assert len(result["times"]) == 3  # 3个tick
        assert len(result["prices"]) == 3
        assert result["change"] == 12.0
        assert result["change_percent"] == pytest.approx(0.67, abs=0.01)

    def test_trading_without_orderbook(self, mock_quote_fetcher, mock_calendar_trading):
        """盘中：无盘口提供者 → order_book 为空，但不抛异常"""
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_trading)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["order_book"]["bids"] == []
        assert result["order_book"]["asks"] == []
        assert result["trade_records"] == []

    def test_noon_break(self, mock_quote_fetcher, mock_calendar_noon_break):
        """午休：复用盘中逻辑"""
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_noon_break)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["should_poll"] is True
        assert result["trading_phase"] == TradingPhase.NOON_BREAK.value

    def test_after_close_with_cache(self, mock_quote_fetcher, mock_calendar_after_close, sample_intraday_data):
        """盘后：有缓存 → 返回缓存，should_poll=False"""
        from ..types import IntradayCache
        cache = IntradayCache()
        cache.set("600519", sample_intraday_data)

        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_after_close, cache=cache)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["should_poll"] is False
        assert result["trading_phase"] == TradingPhase.AFTER_CLOSE.value
        assert result["current_price"] == 1800.0

    def test_after_close_no_cache(self, mock_quote_fetcher, mock_calendar_after_close):
        """盘后：无缓存 →  fallback 到盘中逻辑获取当日数据"""
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_after_close)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["should_poll"] is True  # fallback 到盘中逻辑
        assert result["trading_phase"] == TradingPhase.AFTER_CLOSE.value


class TestIntradayProviderCache:
    """缓存行为测试"""

    def test_trading_caches_data(self, mock_quote_fetcher, mock_calendar_trading):
        """盘中获取后应写入缓存"""
        from ..types import IntradayCache
        cache = IntradayCache()
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_trading, cache=cache)

        provider.get_intraday_data("600519")
        cached = cache.get("600519")

        assert cached is not None
        assert cached.symbol == "600519"
        assert cached.current_price == 1800.0
        assert cached.should_poll is True

    def test_before_open_uses_cache(self, mock_quote_fetcher, mock_calendar_before_open):
        """盘前应优先使用缓存"""
        from ..types import IntradayCache
        cache = IntradayCache()
        cached_data = IntradayData(
            symbol="600519", name="贵州茅台",
            current_price=1800.0, yesterday_close=1788.0,
            change=12.0, change_percent=0.67,
            ticks=[IntradayTickRecord(time="09:30", price=1800.0, volume=100, avg_price=1800.0)],
            order_book_bids=[], order_book_asks=[],
            trade_records=[], trade_date=pd.Timestamp("2026-05-14"),
            order_book_message="", trade_records_message="",
            is_index=False, should_poll=True,
        )
        cache.set("600519", cached_data)

        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_before_open, cache=cache)
        result = provider.get_intraday_data("600519")

        assert result["current_price"] == 1800.0
        assert len(result["times"]) == 1


class TestIntradayProviderEdgeCases:
    """边界条件测试"""

    def test_no_calendar_uses_market_time_utils(self, mock_quote_fetcher):
        """无 calendar 时应使用 MarketTimeUtils 判断"""
        provider = IntradayProvider(mock_quote_fetcher)
        result = provider.get_intraday_data("600519")

        # 应正常返回，不抛异常
        assert result is not None
        assert "trading_phase" in result

    def test_quote_none(self, mock_quote_fetcher_fail, mock_calendar_trading):
        """实时行情返回 None → current_price=0"""
        provider = IntradayProvider(mock_quote_fetcher_fail, calendar=mock_calendar_trading)
        result = provider.get_intraday_data("600519")

        assert result is not None
        assert result["current_price"] == 0.0
        assert result["yesterday_close"] == 0.0

    def test_ticks_none(self, mock_quote_fetcher, mock_calendar_trading):
        """分时 tick 返回 None → ticks 为空列表"""
        mock_quote_fetcher.get_intraday_ticks.return_value = None
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_trading)
        result = provider.get_intraday_data("600519")

        assert result["times"] == []
        assert result["prices"] == []

    def test_exception_returns_none(self, mock_quote_fetcher, mock_calendar_trading):
        """严重异常时返回 None（安全回退）"""
        mock_quote_fetcher.get_realtime_quote.side_effect = RuntimeError("boom")
        provider = IntradayProvider(mock_quote_fetcher, calendar=mock_calendar_trading)
        result = provider.get_intraday_data("600519")

        assert result is None

    def test_frontend_data_structure(self, mock_quote_fetcher, mock_calendar_trading, mock_orderbook_provider):
        """验证前端兼容的数据结构"""
        provider = IntradayProvider(
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            orderbook_provider=mock_orderbook_provider,
        )
        result = provider.get_intraday_data("600519")

        # 前端 intraday_chart.js 期望的字段
        required_fields = [
            "symbol", "name", "current_price", "yesterday_close",
            "change", "change_percent",
            "times", "prices", "volumes", "avg_prices",
            "order_book", "trade_records",
            "should_poll", "is_index",
        ]
        for field in required_fields:
            assert field in result, f"缺少前端字段: {field}"

        # order_book 结构
        assert "bids" in result["order_book"]
        assert "asks" in result["order_book"]


class TestIntradayProviderHelpers:
    """内部方法测试"""

    def test_calc_change_percent_normal(self):
        """正常涨跌幅计算"""
        result = IntradayProvider._calc_change_percent(1800.0, 1788.0)
        assert result == pytest.approx(0.67, abs=0.01)

    def test_calc_change_percent_none(self):
        """None 输入 → 0.0"""
        assert IntradayProvider._calc_change_percent(None, 1788.0) == 0.0
        assert IntradayProvider._calc_change_percent(1800.0, None) == 0.0

    def test_calc_change_percent_zero_yesterday(self):
        """昨收为 0 → 0.0"""
        assert IntradayProvider._calc_change_percent(1800.0, 0.0) == 0.0

    def test_df_to_ticks(self):
        """DataFrame → IntradayTickRecord 列表"""
        df = pd.DataFrame({
            "time": ["09:30", "09:31"],
            "price": [1800.0, 1801.0],
            "volume": [100, 200],
            "avg_price": [1800.0, 1800.5],
        })
        ticks = IntradayProvider._df_to_ticks(df)

        assert len(ticks) == 2
        assert ticks[0].time == "09:30"
        assert ticks[0].price == 1800.0
        assert ticks[0].volume == 100

    def test_build_empty_intraday_data(self):
        """空数据构建"""
        data = IntradayProvider._build_empty_intraday_data("600519", pd.Timestamp("2026-05-14"))

        assert data.symbol == "600519"
        assert data.current_price == 0.0
        assert data.ticks == []
        assert data.should_poll is True
