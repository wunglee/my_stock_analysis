"""数据提供者适配器

将当前项目的 DataFetcherManager 适配为 HistoricalDataProvider 接口，
使 ChartDataAssembler 可以无缝使用当前项目的多数据源 + 故障切换能力。
"""

import logging
from typing import Dict, Any, Optional

import pandas as pd

from src.chart_legacy.market_types import PriceData, OHLCVRecord, IntradayData, IntradayTickRecord, OrderBookLevel, TradeDetailRecord, TickRange
from src.chart_legacy.market_enums import MarketCode, TradingPhase
from src.chart_legacy.market_time_utils import MarketTimeUtils, _infer_market_from_symbol

logger = logging.getLogger(__name__)


class DataFetcherAdapter:
    """DataFetcherManager 适配器

    实现 ChartDataAssembler 所需的 get_index_prices 接口，
    内部委托给当前项目的 DataFetcherManager。
    """

    def __init__(self, manager=None):
        """初始化适配器

        Args:
            manager: DataFetcherManager 实例（可选，默认创建新实例）
        """
        if manager is None:
            from data_provider.base import DataFetcherManager
            manager = DataFetcherManager()
        self._manager = manager
        self._memory_cache: Dict[str, Any] = {}

    def get_index_prices(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        market_local_time: pd.Timestamp,
        period: str = 'daily',
    ) -> PriceData:
        """获取指数/个股价格数据

        委托给 DataFetcherManager.get_daily_data()，然后将 DataFrame
        转换为 PriceData。

        Args:
            symbol: 股票代码（如 '600519', 'AAPL', 'HK00700'）
            start_date: 开始日期
            end_date: 结束日期
            market_local_time: 市场本地时间（当前未使用，保留接口兼容）
            period: 周期（daily/weekly/monthly，当前仅支持 daily）

        Returns:
            PriceData: 标准化的价格数据对象
        """
        try:
            # 格式化日期为字符串
            start_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, pd.Timestamp) else str(start_date)
            end_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, pd.Timestamp) else str(end_date)

            logger.info(f"[Adapter] 获取数据: {symbol}, {start_str} ~ {end_str}")

            # 委托给 DataFetcherManager
            df, source_name = self._manager.get_daily_data(
                stock_code=symbol,
                start_date=start_str,
                end_date=end_str,
            )

            if df is None or df.empty:
                logger.warning(f"[Adapter] {symbol} 无数据")
                return PriceData(
                    records=[],
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    count=0,
                )

            # DataFrame -> PriceData
            price_data = PriceData.from_dataframe(df, symbol=symbol)
            logger.info(f"[Adapter] {symbol} 获取成功: {price_data.count} 条 (来源: {source_name})")
            return price_data

        except Exception as e:
            logger.error(f"[Adapter] 获取 {symbol} 失败: {e}")
            # 返回空数据而非抛异常，保持 ChartDataAssembler 的容错逻辑
            return PriceData(
                records=[],
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                count=0,
            )

    def get_stock_prices(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        market_local_time: pd.Timestamp,
        period: str = 'daily',
    ) -> PriceData:
        """获取个股价格数据（与 get_index_prices 逻辑相同）"""
        return self.get_index_prices(symbol, start_date, end_date, market_local_time, period)

    def get_index_returns(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.Series:
        """获取收益率序列（预留实现）"""
        price_data = self.get_index_prices(symbol, start_date, end_date, start_date)
        if price_data.count < 2:
            return pd.Series(dtype=float)
        closes = pd.Series([r.close for r in price_data.records])
        returns = closes.pct_change().dropna()
        return returns

    def get_intraday_data(
        self,
        symbol: str,
        tick_range: Optional[TickRange] = None,
        market_local_time: pd.Timestamp = None,
    ) -> IntradayData:
        """获取分时数据（预留实现）

        当前返回空结构，避免 ChartDataAssembler 崩溃。
        后续接入真实数据源时需替换实现。
        """
        logger.warning(f"[Adapter] get_intraday_data 尚未实现: {symbol}")
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
            trade_date=pd.Timestamp.now(),
            order_book_message='分时数据尚未实现',
            trade_records_message='分时数据尚未实现',
            is_index=False,
            should_poll=False,
        )

    def get_all_symbols(self, market: MarketCode) -> pd.DataFrame:
        """获取市场全部股票代码（预留实现）"""
        logger.warning(f"[Adapter] get_all_symbols 尚未实现: {market}")
        return pd.DataFrame(columns=['symbol', 'name', 'markets'])

    def get_complete_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """获取完整基本面数据（预留实现）"""
        logger.warning(f"[Adapter] get_complete_fundamental_data 尚未实现: {symbol}")
        return {}

    def _set_to_memory_cache_obj(self, key: str, value: Any) -> None:
        """内存缓存接口（实际存储）"""
        self._memory_cache[key] = value

    def get_realtime_kline(self, symbol: str, period: str = 'daily') -> Dict[str, Any]:
        """获取实时K线数据（当日K柱）

        基于 DataFetcherManager.get_realtime_quote() 返回的 UnifiedRealtimeQuote
        直接组装当日 open/high/low/close/volume，无需复杂聚合。

        Args:
            symbol: 股票代码
            period: 周期（daily/weekly/monthly）

        Returns:
            {
                'date': str,
                'open': float, 'high': float, 'low': float, 'close': float, 'volume': int,
                'trading_phase': str, 'should_poll': bool
            }
        """
        market_local_time = MarketTimeUtils.get_market_time_now(symbol)
        market_code = MarketCode.parse(_infer_market_from_symbol(symbol))
        trading_phase = MarketTimeUtils.determine_trading_phase(market_code, market_local_time)
        trade_date = market_local_time.strftime('%Y-%m-%d')

        # 盘后：不轮询，返回空结构
        if trading_phase == TradingPhase.AFTER_CLOSE:
            return {
                'date': trade_date,
                'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0,
                'trading_phase': trading_phase.value,
                'should_poll': False,
            }

        # 获取实时行情
        quote = self._manager.get_realtime_quote(symbol)
        if quote is None or not quote.has_basic_data():
            logger.warning(f"[Adapter] 无法获取 {symbol} 实时行情")
            return {
                'date': trade_date,
                'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0,
                'trading_phase': trading_phase.value,
                'should_poll': True,
            }

        # 组装当日K柱
        kline = {
            'date': trade_date,
            'open': quote.open_price,
            'high': quote.high,
            'low': quote.low,
            'close': quote.price,
            'volume': quote.volume,
            'trading_phase': trading_phase.value,
            'should_poll': True,
        }

        # 周线/月线：合并到最后一个周期K柱
        if period in ('weekly', 'monthly'):
            kline = self._merge_realtime_to_period(symbol, period, kline)

        return kline

    def _merge_realtime_to_period(self, symbol: str, period: str, realtime_kline: Dict[str, Any]) -> Dict[str, Any]:
        """将当日实时K线合并到周线/月线的最后一个K柱

        逻辑：
        - 如果当日是新周/新月的第一天 → 创建新K柱
        - 否则 → 合并 high/low/close/volume 到最后一个历史K柱
        """
        cache_key = f"last_period_bar_{symbol}_{period}"
        last_bar = self._memory_cache.get(cache_key)

        # 缓存未命中：主动查询历史数据作为 fallback
        if not last_bar:
            logger.warning(f"[Adapter] {period}线缓存未命中，查询历史数据")
            try:
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)
                end_date = market_local_time
                start_date = end_date - pd.Timedelta(days=60)
                price_data = self.get_index_prices(symbol, start_date, end_date, market_local_time, period)
                if price_data and price_data.count > 0:
                    last_record = price_data.records[-1]
                    last_bar = {
                        'date': last_record.date.strftime('%Y-%m-%d'),
                        'open': float(last_record.open),
                        'high': float(last_record.high),
                        'low': float(last_record.low),
                        'close': float(last_record.close),
                        'volume': int(last_record.volume),
                    }
                    # 回填缓存，下次命中
                    self._memory_cache[cache_key] = last_bar
                else:
                    logger.warning(f"[Adapter] {period}线历史数据为空，返回原始实时K线")
                    return realtime_kline
            except Exception as e:
                logger.warning(f"[Adapter] 查询历史数据失败: {e}，返回原始实时K线")
                return realtime_kline

        realtime_date = pd.Timestamp(realtime_kline['date'])
        last_date = pd.Timestamp(last_bar['date'])

        # 判断是否需要创建新K柱
        should_create_new = False
        if period == 'weekly':
            should_create_new = (
                realtime_date.isocalendar()[0] != last_date.isocalendar()[0]
                or realtime_date.isocalendar()[1] != last_date.isocalendar()[1]
            )
        elif period == 'monthly':
            should_create_new = (
                realtime_date.year != last_date.year
                or realtime_date.month != last_date.month
            )

        if should_create_new:
            logger.info(f"[Adapter] {period}线 - 创建新K柱: {realtime_kline['date']}")
            return realtime_kline

        # 合并到最后一个K柱
        logger.info(f"[Adapter] {period}线 - 合并K柱: {last_bar['date']} <- {realtime_kline['date']}")
        return {
            'date': last_bar['date'],
            'open': last_bar['open'],
            'high': max(last_bar['high'], realtime_kline['high'] or last_bar['high']),
            'low': min(last_bar['low'], realtime_kline['low'] or last_bar['low']),
            'close': realtime_kline['close'],
            'volume': (last_bar.get('volume', 0) or 0) + (realtime_kline.get('volume', 0) or 0),
            'trading_phase': realtime_kline['trading_phase'],
            'should_poll': realtime_kline['should_poll'],
        }
