"""
实时K线提供者 — 日/周/月实时K线

职责：
1. 获取当日实时行情（open/high/low/close/volume）
2. 日线：直接返回实时行情组装成的K柱
3. 周线/月线：
   a. 通过 IDataProvider 获取本周/本月历史日线
   b. 用 BarAggregator 聚合成周/月K柱
   c. 将当日实时行情合并到最后一个K柱

关键：不缓存周/月线，每次实时聚合 + 合并。
      因此不存在陈旧K柱问题（与 history_provider 设计一致）。

融合三处旧实现的优点：
- base_provider: 纯函数合并逻辑（无缓存、无外部查询）
- hybrid_provider: 自动查历史、自动判断新周期
- data_provider_adapter: 统一入口、trading_phase 判断
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from core.share.market.market_enums import TradingPhase
from core.share.market.market_time_utils import MarketTimeUtils
from core.share.market.market_utils import MarketUtils

from .types import RealtimeKline

if TYPE_CHECKING:
    from ..history_provider.interface import IDataProvider
    from .interface import IQuoteFetcher, ITradingCalendar

logger = logging.getLogger(__name__)


class RealtimeKlineProvider:
    """实时K线提供者"""

    def __init__(
        self,
        history_provider: IDataProvider,
        quote_fetcher: IQuoteFetcher,
        calendar: ITradingCalendar | None = None,
        bar_aggregator=None,
    ) -> None:
        self._history = history_provider
        self._quote = quote_fetcher
        self._calendar = calendar

        if bar_aggregator is None:
            from data_provider.bar_aggregator import BarAggregator
            bar_aggregator = BarAggregator()
        self._bar_aggregator = bar_aggregator

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_realtime_kline(
        self,
        symbol: str,
        period: str = "daily",
    ) -> RealtimeKline | None:
        """获取实时K线

        Args:
            symbol: 股票代码
            period: 'daily' | 'weekly' | 'monthly'

        Returns:
            RealtimeKline: 单条K柱数据 + trading_phase + should_poll
            None: 严重异常时的安全回退
        """
        try:
            return self._get_realtime_kline_internal(symbol, period)
        except Exception as e:
            logger.exception(f"[RealtimeKline] {symbol} {period} 获取异常: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _get_realtime_kline_internal(
        self, symbol: str, period: str
    ) -> RealtimeKline:
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

        trade_date = market_local_time.strftime("%Y-%m-%d")

        # 盘后：不轮询，返回空结构
        if trading_phase == TradingPhase.AFTER_CLOSE:
            return RealtimeKline.empty(
                trade_date=trade_date,
                trading_phase=trading_phase.value,
                should_poll=False,
            )

        # 获取实时行情
        quote = self._quote.get_realtime_quote(symbol)
        if quote is None or not self._has_basic_data(quote):
            logger.warning(f"[RealtimeKline] 无法获取 {symbol} 实时行情")
            return RealtimeKline.empty(
                trade_date=trade_date,
                trading_phase=trading_phase.value,
                should_poll=True,
            )

        # 组装当日K柱
        daily_kline = RealtimeKline.from_quote(
            quote=quote,
            trade_date=trade_date,
            trading_phase=trading_phase.value,
            should_poll=True,
        )

        if period == "daily":
            return daily_kline

        # 周/月线：获取历史 + 聚合 + 合并
        return self._build_period_kline(symbol, period, daily_kline, market_local_time)

    def _build_period_kline(
        self,
        symbol: str,
        period: str,
        daily_kline: RealtimeKline,
        market_local_time: pd.Timestamp,
    ) -> RealtimeKline:
        """构建周/月实时K线"""
        # 计算本周/本月的起始日期
        start_date = self._get_period_start(period, market_local_time)
        end_date = market_local_time.normalize()

        # 获取历史日线
        history_df = self._history.fetch(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period="daily",
        )

        if history_df is None or history_df.empty:
            logger.warning(
                f"[RealtimeKline] {symbol} {period} 无历史数据，返回当日K柱"
            )
            return daily_kline

        # 聚合为周/月K柱
        if period == "weekly":
            period_df = self._bar_aggregator.daily_to_weekly(history_df)
        elif period == "monthly":
            period_df = self._bar_aggregator.daily_to_monthly(history_df)
        else:
            raise ValueError(f"不支持的周期: {period}")

        if period_df is None or period_df.empty:
            return daily_kline

        # 获取最后一个周期K柱
        last_bar = period_df.iloc[-1].copy()

        # 判断当日是否为新周期第一天
        if self._is_new_period(market_local_time, last_bar["trade_date"], period):
            # 新周期：当日K柱即为新周期的第一个K柱
            return daily_kline

        # 合并当日实时行情到最后一个周期K柱
        merged = self._merge_realtime_to_period(last_bar, daily_kline)

        return RealtimeKline(
            date=merged.get("date", daily_kline.date),
            open=merged.get("open"),
            high=merged.get("high"),
            low=merged.get("low"),
            close=merged.get("close"),
            volume=merged.get("volume", 0),
            turnover_rate=daily_kline.turnover_rate,
            trading_phase=daily_kline.trading_phase,
            should_poll=daily_kline.should_poll,
        )

    @staticmethod
    def _merge_realtime_to_period(
        period_bar: pd.Series,
        realtime: RealtimeKline,
    ) -> dict:
        """将当日实时行情合并到周期K柱

        合并规则（与现有三处实现一致）：
        - open:  保持 period_bar.open（周期第一天的开盘价）
        - high:  max(period_bar.high, realtime.high)
        - low:   min(period_bar.low, realtime.low)
        - close: realtime.close（最新价）
        - volume: period_bar.volume + realtime.volume
        """
        period_open = period_bar.get("open")
        period_high = period_bar.get("high")
        period_low = period_bar.get("low")
        period_volume = period_bar.get("volume", 0)
        if pd.isna(period_volume):
            period_volume = 0

        realtime_high = realtime.high if realtime.high is not None else period_high
        realtime_low = realtime.low if realtime.low is not None else period_low
        realtime_close = realtime.close if realtime.close is not None else period_bar.get("close")
        realtime_volume = realtime.volume if realtime.volume is not None else 0

        return {
            "date": period_bar.get("trade_date", realtime.date),
            "open": period_open,
            "high": max(period_high, realtime_high) if period_high is not None else realtime_high,
            "low": min(period_low, realtime_low) if period_low is not None else realtime_low,
            "close": realtime_close,
            "volume": (period_volume or 0) + (realtime_volume or 0),
        }

    @staticmethod
    def _is_new_period(
        current_date: pd.Timestamp,
        last_period_date: pd.Timestamp,
        period: str,
    ) -> bool:
        """判断当日是否为新周期第一天"""
        current_norm = pd.to_datetime(current_date).normalize()
        last_norm = pd.to_datetime(last_period_date).normalize()

        if current_norm == last_norm:
            return False

        if period == "weekly":
            # ISO 周：周一为新周第一天
            return current_norm.isocalendar()[:2] != last_norm.isocalendar()[:2]
        elif period == "monthly":
            return (current_norm.year, current_norm.month) != (
                last_norm.year,
                last_norm.month,
            )
        return False

    @staticmethod
    def _get_period_start(period: str, market_local_time: pd.Timestamp) -> pd.Timestamp:
        """获取当前周期的起始日期"""
        today = market_local_time.normalize()

        if period == "weekly":
            # 本周一
            return today - pd.Timedelta(days=today.weekday())
        elif period == "monthly":
            # 本月1日
            return pd.Timestamp(today.year, today.month, 1)
        else:
            return today

    @staticmethod
    def _has_basic_data(quote) -> bool:
        """检查实时行情是否有基本数据"""
        return (
            hasattr(quote, "price")
            and quote.price is not None
            and hasattr(quote, "open_price")
            and quote.open_price is not None
        )
