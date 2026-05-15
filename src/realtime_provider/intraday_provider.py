"""
分时数据提供者 — 交易时段感知

职责：
1. 根据 TradingPhase 决定分时数据策略
2. 盘中：获取实时tick + 盘口 + 成交明细
3. 盘前/午休：返回昨日缓存或空数据，标记 should_poll=True
4. 盘后：返回当日完整分时，标记 should_poll=False

提取自 base_provider.py:get_intraday_data() 的4个分支逻辑。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from src.chart_legacy.market_types import IntradayData, IntradayTickRecord
from src.chart_legacy.market_enums import TradingPhase
from src.chart_legacy.market_time_utils import MarketTimeUtils
from src.chart_legacy.market_utils import MarketUtils

from .types import IntradayCache

if TYPE_CHECKING:
    from .interface import IQuoteFetcher, ITradingCalendar
    from .orderbook_provider import OrderBookProvider

logger = logging.getLogger(__name__)


class IntradayProvider:
    """分时数据提供者"""

    def __init__(
        self,
        quote_fetcher: IQuoteFetcher,
        calendar: ITradingCalendar | None = None,
        orderbook_provider: OrderBookProvider | None = None,
        cache: IntradayCache | None = None,
    ) -> None:
        self._quote = quote_fetcher
        self._calendar = calendar
        self._orderbook = orderbook_provider
        self._cache = cache or IntradayCache()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_intraday_data(
        self,
        symbol: str,
        tick_range=None,
    ) -> dict | None:
        """获取分时数据（交易时段感知）

        根据当前交易时段自动选择数据源：
        - BEFORE_OPEN: 返回昨日缓存（如有），should_poll=True
        - TRADING: 获取实时tick + 盘口 + 成交明细，should_poll=True
        - NOON_BREAK: 获取上午tick + 收盘盘口，should_poll=True
        - AFTER_CLOSE: 返回当日完整缓存，should_poll=False

        Args:
            symbol: 股票代码
            tick_range: TickRange 对象（可选）

        Returns:
            dict: 前端兼容的分时数据结构
            None: 严重异常时的安全回退
        """
        try:
            return self._get_intraday_data_internal(symbol, tick_range)
        except Exception as e:
            logger.exception(f"[Intraday] {symbol} 获取分时数据异常: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Internal — 按交易时段分派
    # ------------------------------------------------------------------ #
    def _get_intraday_data_internal(
        self, symbol: str, tick_range
    ) -> dict:
        """内部实现（不含异常兜底）"""
        market_local_time = MarketTimeUtils.get_market_time_now(symbol)
        market_code = MarketUtils.infer_market_from_symbol(symbol)

        # 交易时段判断
        if self._calendar is not None:
            trading_phase = self._calendar.determine_trading_phase(
                symbol, market_local_time
            )
        else:
            trading_phase = MarketTimeUtils.determine_trading_phase(
                market_code, market_local_time
            )

        trade_date = market_local_time.normalize()

        # 按交易时段分派处理
        if trading_phase == TradingPhase.BEFORE_OPEN:
            intraday_data = self._handle_before_open(symbol, trade_date)
        elif trading_phase == TradingPhase.TRADING:
            intraday_data = self._handle_trading(symbol, trade_date, tick_range)
        elif trading_phase == TradingPhase.NOON_BREAK:
            intraday_data = self._handle_noon_break(symbol, trade_date)
        elif trading_phase == TradingPhase.AFTER_CLOSE:
            intraday_data = self._handle_after_close(symbol, trade_date)
        else:
            intraday_data = self._build_empty_intraday_data(symbol, trade_date)

        # 转换为前端兼容的 dict
        return self._to_api_dict(intraday_data, trading_phase)

    def _handle_before_open(
        self, symbol: str, trade_date: pd.Timestamp
    ) -> IntradayData:
        """盘前：返回昨日缓存或空数据"""
        # 尝试获取昨日缓存
        cached = self._cache.get(symbol)
        if cached is not None:
            return cached

        return self._build_empty_intraday_data(symbol, trade_date)

    def _handle_trading(
        self,
        symbol: str,
        trade_date: pd.Timestamp,
        tick_range,
    ) -> IntradayData:
        """盘中：获取实时tick + 盘口 + 成交明细"""
        # 获取分时tick数据
        ticks_df = self._quote.get_intraday_ticks(symbol)

        # 获取盘口和成交明细
        order_book_bids, order_book_asks = [], []
        trade_records = []
        if self._orderbook is not None:
            snapshot = self._orderbook.get_order_book(symbol)
            if snapshot is not None:
                order_book_bids = snapshot.bids
                order_book_asks = snapshot.asks
            trade_records_raw = self._orderbook.get_trade_records(symbol)
            if trade_records_raw is not None:
                trade_records = trade_records_raw

        # 获取实时行情作为当前价格
        current_price, yesterday_close = self._get_prices(symbol)

        # 构建 IntradayData
        ticks = self._df_to_ticks(ticks_df) if ticks_df is not None else []

        data = IntradayData(
            symbol=symbol,
            name=symbol,
            current_price=current_price or 0.0,
            yesterday_close=yesterday_close or 0.0,
            change=(current_price or 0.0) - (yesterday_close or 0.0),
            change_percent=self._calc_change_percent(current_price, yesterday_close),
            ticks=ticks,
            order_book_bids=order_book_bids,
            order_book_asks=order_book_asks,
            trade_records=[
                {
                    "time": r.time if hasattr(r, "time") else r.get("time"),
                    "price": r.price if hasattr(r, "price") else r.get("price"),
                    "volume": r.volume if hasattr(r, "volume") else r.get("volume"),
                    "direction": (r.direction if hasattr(r, "direction") else r.get("type", r.get("direction"))),
                }
                for r in trade_records
            ] if trade_records else [],
            trade_date=trade_date,
            order_book_message="",
            trade_records_message="",
            is_index=False,
            should_poll=True,
        )

        # 缓存
        self._cache.set(symbol, data)
        return data

    def _handle_noon_break(
        self, symbol: str, trade_date: pd.Timestamp
    ) -> IntradayData:
        """午休：获取上午tick + 收盘盘口"""
        # 复用盘中逻辑，但限制时间范围到上午收盘
        # 简化实现：直接获取完整数据，前端自行处理
        return self._handle_trading(symbol, trade_date, None)

    def _handle_after_close(
        self, symbol: str, trade_date: pd.Timestamp
    ) -> IntradayData:
        """盘后：返回当日完整缓存"""
        cached = self._cache.get(symbol)
        if cached is not None:
            # 更新为不轮询
            cached.should_poll = False
            return cached

        # 无缓存时尝试获取当日数据
        return self._handle_trading(symbol, trade_date, None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_empty_intraday_data(
        symbol: str, trade_date: pd.Timestamp
    ) -> IntradayData:
        """构建空的分时数据"""
        return IntradayData(
            symbol=symbol,
            name=symbol,
            current_price=0.0,
            yesterday_close=0.0,
            change=0.0,
            change_percent=0.0,
            ticks=[],
            order_book_bids=[],
            order_book_asks=[],
            trade_records=[],
            trade_date=trade_date,
            order_book_message="",
            trade_records_message="",
            is_index=False,
            should_poll=True,
        )

    def _get_prices(self, symbol: str) -> tuple[float | None, float | None]:
        """获取当前价格和昨收价"""
        quote = self._quote.get_realtime_quote(symbol)
        if quote is None:
            return None, None
        current_price = getattr(quote, "price", None)
        yesterday_close = getattr(quote, "pre_close", None)
        return current_price, yesterday_close

    @staticmethod
    def _calc_change_percent(current: float | None, yesterday: float | None) -> float:
        """计算涨跌幅"""
        if current is None or yesterday is None or yesterday == 0:
            return 0.0
        return round((current - yesterday) / yesterday * 100, 2)

    @staticmethod
    def _df_to_ticks(df: pd.DataFrame) -> list[IntradayTickRecord]:
        """将 DataFrame 转换为 IntradayTickRecord 列表"""
        ticks = []
        for _, row in df.iterrows():
            ticks.append(
                IntradayTickRecord(
                    time=str(row.get("time", "")),
                    price=float(row.get("price", 0.0)),
                    volume=int(row.get("volume", 0)),
                    avg_price=float(row.get("avg_price", 0.0)),
                )
            )
        return ticks

    @staticmethod
    def _to_api_dict(data: IntradayData, trading_phase: TradingPhase) -> dict:
        """将 IntradayData 转换为前端兼容的 dict

        前端 intraday_chart.js 期望的数据结构：
        {
            symbol, name, current_price, yesterday_close, change, change_percent,
            times[], prices[], volumes[], avg_prices[],
            order_book: {bids[], asks[]},
            trade_records[],
            should_poll, is_index
        }
        """
        return {
            "symbol": data.symbol,
            "name": data.name,
            "current_price": data.current_price,
            "yesterday_close": data.yesterday_close,
            "change": data.change,
            "change_percent": data.change_percent,
            "times": [t.time for t in data.ticks],
            "prices": [t.price for t in data.ticks],
            "volumes": [t.volume for t in data.ticks],
            "avg_prices": [t.avg_price for t in data.ticks],
            "order_book": {
                "bids": [
                    {"price": b.price, "volume": b.volume}
                    for b in data.order_book_bids
                ],
                "asks": [
                    {"price": a.price, "volume": a.volume}
                    for a in data.order_book_asks
                ],
            },
            "trade_records": [
                {
                    "time": r.time if hasattr(r, "time") else r.get("time"),
                    "price": r.price if hasattr(r, "price") else r.get("price"),
                    "volume": r.volume if hasattr(r, "volume") else r.get("volume"),
                    "type": (r.direction if hasattr(r, "direction") else r.get("type", r.get("direction"))),
                }
                for r in data.trade_records
            ] if data.trade_records else [],
            "should_poll": data.should_poll,
            "is_index": getattr(data, "is_index", False),
            "trading_phase": trading_phase.value,
        }
