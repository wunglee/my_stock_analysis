"""
HistoryProviderAdapter — 将 ThreeLayerProvider 适配为 ChartDataAssembler 接口

职责：
1. 把 IDataProvider.fetch() 返回的 DataFrame 转为 PriceData
2. 根据交易时段设置 needs_realtime_kline
3. 可选接入 IntradayProvider 提供分时数据
4. 提供 _set_to_memory_cache_obj 兼容方法
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pandas as pd

from src.chart_legacy.market_types import PriceData, OHLCVRecord, IntradayData, TickRange
from src.chart_legacy.market_enums import TradingPhase
from src.chart_legacy.market_time_utils import MarketTimeUtils
from src.chart_legacy.market_utils import MarketUtils

if TYPE_CHECKING:
    from .interface import IDataProvider
    from src.realtime_provider import IntradayProvider, RealtimeKlineProvider
    from src.realtime_provider.interface import IQuoteFetcher


class DataFetcherManagerQuoteFetcher:
    """将 DataFetcherManager 适配为 IQuoteFetcher 接口

    DataFetcherManager 只支持 get_realtime_quote，
    分时/盘口/逐笔成交在当前项目中暂不支持，返回 None。
    """

    def __init__(self, manager) -> None:
        self._manager = manager

    def get_realtime_quote(self, symbol: str):
        """获取实时行情快照"""
        return self._manager.get_realtime_quote(symbol)

    def get_intraday_ticks(self, symbol: str) -> pd.DataFrame | None:
        """获取当日分时 tick 数据（当前不支持）"""
        return None

    def get_order_book(
        self, symbol: str
    ) -> tuple[list, list] | None:
        """获取盘口数据（当前不支持）"""
        return None

    def get_trade_records(self, symbol: str) -> list | None:
        """获取逐笔成交记录（当前不支持）"""
        return None

logger = logging.getLogger(__name__)


class HistoryProviderAdapter:
    """历史数据提供者适配器

    包装 ThreeLayerProvider，对外暴露 ChartDataAssembler 期望的接口：
    - get_index_prices(symbol, start_date, end_date, market_local_time, period)
    - get_intraday_data(symbol, tick_range)
    - _set_to_memory_cache_obj(key, value)
    """

    def __init__(
        self,
        history_provider: IDataProvider,
        intraday_provider: IntradayProvider | None = None,
    ) -> None:
        self._history = history_provider
        self._intraday = intraday_provider
        self._memory_cache: dict[str, Any] = {}
        self._realtime_kline_provider: RealtimeKlineProvider | None = None

    # ------------------------------------------------------------------ #
    # K线数据接口
    # ------------------------------------------------------------------ #
    def get_index_prices(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        market_local_time: pd.Timestamp,
        period: str = "daily",
    ) -> PriceData:
        """获取K线数据（适配 ChartDataAssembler）

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            market_local_time: 市场本地时间（用于判断 needs_realtime_kline）
            period: 'daily' | 'weekly' | 'monthly'

        Returns:
            PriceData: 价格数据对象
        """
        df = self._history.fetch(symbol, start_date, end_date, period)

        if df is None or df.empty:
            logger.warning(f"[Adapter] {symbol} 无历史数据")
            return PriceData(
                records=[],
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                count=0,
            )

        # DataFrame 列名标准化：trade_date -> date
        if "trade_date" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"trade_date": "date"})

        price_data = PriceData.from_dataframe(df, symbol)

        # 设置 needs_realtime_kline 标记
        self._set_needs_realtime_kline(price_data, market_local_time)

        return price_data

    # 别名：与 get_index_prices 完全一致
    get_stock_prices = get_index_prices

    # ------------------------------------------------------------------ #
    # 分时数据接口
    # ------------------------------------------------------------------ #
    def get_intraday_data(
        self,
        symbol: str,
        tick_range: TickRange | None = None,
        market_local_time: pd.Timestamp | None = None,
    ) -> IntradayData:
        """获取分时数据

        如果传入了 IntradayProvider，则委托给它；
        否则抛出 NotImplementedError。
        """
        if self._intraday is not None:
            result = self._intraday.get_intraday_data(symbol, tick_range)
            if result is None:
                raise RuntimeError(f"获取分时数据失败: {symbol}")
            # 将 dict 转为 IntradayData（如果返回的是 dict）
            if isinstance(result, dict):
                return self._dict_to_intraday_data(result, symbol)
            return result

        raise NotImplementedError(
            "未配置 IntradayProvider，无法获取分时数据"
        )

    # ------------------------------------------------------------------ #
    # 实时K线接口
    # ------------------------------------------------------------------ #
    def get_realtime_kline(
        self,
        symbol: str,
        period: str = "daily",
    ) -> dict[str, Any]:
        """获取实时K线数据（当日K柱）

        委托给 RealtimeKlineProvider，首次调用时延迟初始化。
        """
        if self._realtime_kline_provider is None:
            from data_provider.base import DataFetcherManager
            from src.realtime_provider import RealtimeKlineProvider

            fetcher_mgr = DataFetcherManager()
            quote_fetcher = DataFetcherManagerQuoteFetcher(fetcher_mgr)
            self._realtime_kline_provider = RealtimeKlineProvider(
                history_provider=self._history,
                quote_fetcher=quote_fetcher,
            )

        result = self._realtime_kline_provider.get_realtime_kline(symbol, period)
        if result is None:
            return {
                "date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume": 0,
                "trading_phase": "unknown",
                "should_poll": False,
            }
        return result.to_dict()

    # ------------------------------------------------------------------ #
    # 内存缓存兼容接口
    # ------------------------------------------------------------------ #
    def _set_to_memory_cache_obj(self, key: str, value: Any) -> None:
        """设置内存缓存（兼容 ChartDataAssembler 的缓存操作）"""
        self._memory_cache[key] = value

    def _get_from_memory_cache(self, key: str) -> Any | None:
        """获取内存缓存"""
        return self._memory_cache.get(key)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _set_needs_realtime_kline(
        price_data: PriceData, market_local_time: pd.Timestamp
    ) -> None:
        """根据交易时段设置 needs_realtime_kline 标记"""
        market_code = MarketUtils.infer_market_from_symbol(price_data.symbol)
        market_local_time = MarketTimeUtils.to_market_time_by_symbol(
            market_local_time, price_data.symbol
        )
        trading_phase = MarketTimeUtils.determine_trading_phase(
            market_code, market_local_time
        )

        price_data.needs_realtime_kline = trading_phase in (
            TradingPhase.BEFORE_OPEN,
            TradingPhase.TRADING,
            TradingPhase.NOON_BREAK,
        )

    @staticmethod
    def _dict_to_intraday_data(data: dict, symbol: str) -> IntradayData:
        """将 dict 转换为 IntradayData"""
        from src.chart_legacy.market_types import IntradayTickRecord, OrderBookLevel

        ticks = [
            IntradayTickRecord(
                time=t.get("time", ""),
                price=float(t.get("price", 0)),
                volume=int(t.get("volume", 0)),
                avg_price=float(t.get("avg_price", 0)),
            )
            for t in data.get("ticks", [])
        ]

        order_book_bids = [
            OrderBookLevel(price=b.get("price", 0), volume=b.get("volume", 0))
            for b in data.get("order_book", {}).get("bids", [])
        ]
        order_book_asks = [
            OrderBookLevel(price=a.get("price", 0), volume=a.get("volume", 0))
            for a in data.get("order_book", {}).get("asks", [])
        ]

        trade_records = data.get("trade_records", [])
        if isinstance(trade_records, dict):
            trade_records = trade_records.get("items", [])

        from src.chart_legacy.market_types import TradeDetailRecord

        trade_records_obj = [
            TradeDetailRecord(
                time=r.get("time", ""),
                price=float(r.get("price", 0)),
                volume=int(r.get("volume", 0)),
                direction=r.get("type", ""),
            )
            for r in trade_records
        ]

        return IntradayData(
            symbol=data.get("symbol", symbol),
            name=data.get("name", symbol),
            current_price=float(data.get("current_price", 0)),
            yesterday_close=float(data.get("yesterday_close", 0)),
            change=float(data.get("change", 0)),
            change_percent=float(data.get("change_percent", 0)),
            ticks=ticks,
            order_book_bids=order_book_bids,
            order_book_asks=order_book_asks,
            trade_records=trade_records_obj,
            trade_date=pd.to_datetime(data.get("trade_date", pd.Timestamp.now())),
            order_book_message=data.get("order_book_message", ""),
            trade_records_message=data.get("trade_records_message", ""),
            is_index=data.get("is_index", False),
            should_poll=data.get("should_poll", False),
        )
