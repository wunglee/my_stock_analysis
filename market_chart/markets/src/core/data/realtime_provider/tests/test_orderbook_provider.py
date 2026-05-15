"""
OrderBookProvider 单元测试

职责：纯透传 IQuoteFetcher，无业务逻辑。
测试重点：异常兜底、返回结构标准化。
"""

from __future__ import annotations

import pytest

from core.data.providers.protocols import OrderBookLevel

from ..orderbook_provider import OrderBookProvider


class TestOrderBookProvider:
    """盘口数据提供者测试"""

    # ------------------------------------------------------------------ #
    # get_order_book
    # ------------------------------------------------------------------ #
    def test_get_order_book_success(self, mock_quote_fetcher):
        """正常获取盘口"""
        provider = OrderBookProvider(mock_quote_fetcher)
        result = provider.get_order_book("600519")

        assert result is not None
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        assert result.bids[0].price == 1799.0
        assert result.asks[0].price == 1801.0

    def test_get_order_book_none(self, mock_quote_fetcher_fail):
        """底层返回 None → 本层也返回 None"""
        provider = OrderBookProvider(mock_quote_fetcher_fail)
        result = provider.get_order_book("600519")

        assert result is None

    def test_get_order_book_exception(self, mock_quote_fetcher):
        """底层抛出异常 → 返回 None，不抛异常"""
        mock_quote_fetcher.get_order_book.side_effect = RuntimeError("network error")
        provider = OrderBookProvider(mock_quote_fetcher)

        result = provider.get_order_book("600519")
        assert result is None

    # ------------------------------------------------------------------ #
    # get_trade_records
    # ------------------------------------------------------------------ #
    def test_get_trade_records_success(self, mock_quote_fetcher):
        """正常获取成交明细"""
        provider = OrderBookProvider(mock_quote_fetcher)
        result = provider.get_trade_records("600519")

        assert result is not None
        assert len(result) == 2
        assert result[0]["time"] == "09:30"
        assert result[0]["price"] == 1800.0
        assert result[0]["volume"] == 100
        assert result[0]["type"] == "B"  # direction → type

    def test_get_trade_records_none(self, mock_quote_fetcher_fail):
        """底层返回 None → 本层也返回 None"""
        provider = OrderBookProvider(mock_quote_fetcher_fail)
        result = provider.get_trade_records("600519")

        assert result is None

    def test_get_trade_records_exception(self, mock_quote_fetcher):
        """底层抛出异常 → 返回 None，不抛异常"""
        mock_quote_fetcher.get_trade_records.side_effect = RuntimeError("network error")
        provider = OrderBookProvider(mock_quote_fetcher)

        result = provider.get_trade_records("600519")
        assert result is None

    def test_get_trade_records_empty_list(self, mock_quote_fetcher):
        """底层返回空列表 → 返回标准化空列表"""
        mock_quote_fetcher.get_trade_records.return_value = []
        provider = OrderBookProvider(mock_quote_fetcher)

        result = provider.get_trade_records("600519")
        assert result == []
