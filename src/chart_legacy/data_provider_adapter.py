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
from src.data_provider.bar_aggregator import BarAggregator

logger = logging.getLogger(__name__)


class DataFetcherAdapter:
    """DataFetcherManager 适配器

    实现 ChartDataAssembler 所需的 get_index_prices 接口，
    内部委托给当前项目的 DataFetcherManager。
    """

    def __init__(self, manager=None, caching_provider=None):
        """初始化适配器

        Args:
            manager: DataFetcherManager 实例（可选，默认创建新实例）
            caching_provider: CachingDataProvider 实例（可选，优先使用缓存层）
        """
        self._caching_provider = caching_provider
        if caching_provider is not None:
            # 缓存层已提供，manager 仅用于实时行情等 fallback
            self._manager = manager
        elif manager is None:
            from data_provider.base import DataFetcherManager
            manager = DataFetcherManager()
            self._manager = manager
        else:
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
        转换为 PriceData。支持日线/周线/月线聚合。

        Args:
            symbol: 股票代码（如 '600519', 'AAPL', 'HK00700'）
            start_date: 开始日期
            end_date: 结束日期
            market_local_time: 市场本地时间（当前未使用，保留接口兼容）
            period: 周期（daily/weekly/monthly）

        Returns:
            PriceData: 标准化的价格数据对象
        """
        try:
            # 格式化日期为字符串（用于日志）
            start_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, pd.Timestamp) else str(start_date)
            end_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, pd.Timestamp) else str(end_date)

            logger.info(f"[Adapter] 获取数据: {symbol}, period={period}, {start_str} ~ {end_str}")

            df = None
            source_name = "unknown"

            if self._caching_provider is not None:
                # 优先走缓存层（磁盘缓存优先 + 自动补全）
                # 周线/月线直接走对应缓存方法，利用已聚合的周期缓存
                if period == 'weekly':
                    df = self._caching_provider.get_weekly_bars(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        use_cache=True,
                        auto_save=True,
                    )
                elif period == 'monthly':
                    df = self._caching_provider.get_monthly_bars(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        use_cache=True,
                        auto_save=True,
                    )
                else:
                    df = self._caching_provider.get_daily_bars(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        use_cache=True,
                        auto_save=True,
                    )
                source_name = "cache"
            else:
                # 回退：直接走 DataFetcherManager（仅返回日线，需手动聚合周期）
                df, source_name = self._manager.get_daily_data(
                    stock_code=symbol,
                    start_date=start_str,
                    end_date=end_str,
                )

            # 统一列名转换（CachingDataProvider 返回事实标准列名 trade_date，
            # PriceData.from_dataframe 期望旧列名 date）
            if df is not None and not df.empty:
                df = df.copy()
                if 'trade_date' in df.columns:
                    df = df.rename(columns={'trade_date': 'date'})
                # 去掉 symbol 列（PriceData.from_dataframe 不期望）
                if 'symbol' in df.columns:
                    df = df.drop(columns=['symbol'])

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

            # fallback 路径（无 caching_provider）仍需手动聚合周期
            if self._caching_provider is None and period in ('weekly', 'monthly'):
                market_code = MarketCode.parse(_infer_market_from_symbol(symbol))
                price_data = self._convert_period(price_data, period, market_code)

            logger.info(f"[Adapter] {symbol} 获取成功: {price_data.count} 条 (来源: {source_name}, 周期: {period})")
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

    def _filter_non_trading_periods(self, df: pd.DataFrame, period: str, market_code: MarketCode) -> pd.DataFrame:
        """过滤非交易周期

        从原始组件系统 base_provider.py 迁移。
        智能过滤空周期：只过滤"非交易周/月"（整周/月都是节假日），
        保留"有交易但无数据的周/月"（用于判断上市周）。

        使用当前项目的 trading_calendar.is_market_open 替代原始系统的
        TradingCalendarService。
        """
        from src.core.trading_calendar import is_market_open

        original_count = len(df)
        rows_to_keep = []
        rows_filtered = []

        for idx, row in df.iterrows():
            is_empty = pd.isna(row['open']) and pd.isna(row['high']) and pd.isna(row['low']) and pd.isna(row['close'])

            if is_empty:
                date = pd.Timestamp(row['date'])

                if period == 'weekly':
                    week_start = date - pd.Timedelta(days=date.weekday())
                    week_end = week_start + pd.Timedelta(days=6)
                    period_start, period_end = week_start, week_end
                    period_name = '非交易周'
                elif period == 'monthly':
                    month_start = date.replace(day=1)
                    if date.month == 12:
                        month_end = pd.Timestamp(date.year + 1, 1, 1) - pd.Timedelta(days=1)
                    else:
                        month_end = pd.Timestamp(date.year, date.month + 1, 1) - pd.Timedelta(days=1)
                    period_start, period_end = month_start, month_end
                    period_name = '非交易月'
                else:
                    rows_to_keep.append(idx)
                    continue

                # 检查这个周期是否有任何交易日
                market_str = market_code.value.lower() if market_code != MarketCode.UNKNOWN else 'cn'
                has_trading_day = False
                current_date = period_start
                while current_date <= period_end:
                    if is_market_open(market_str, current_date.date()):
                        has_trading_day = True
                        break
                    current_date += pd.Timedelta(days=1)

                if has_trading_day:
                    rows_to_keep.append(idx)
                else:
                    rows_filtered.append((idx, date, period_name))
            else:
                rows_to_keep.append(idx)

        df_filtered = df.loc[rows_to_keep]

        if rows_filtered:
            logger.info(f"[Adapter] {period}线转换：过滤了 {len(rows_filtered)} 个非交易周期")
            for idx, date, reason in rows_filtered[:5]:
                logger.info(f"   - {date.strftime('%Y-%m-%d')}: {reason}")
            if len(rows_filtered) > 5:
                logger.info(f"   ... 还有 {len(rows_filtered) - 5} 个")
            logger.info(f"   原始{period}线数据: {original_count} 条 → 过滤后: {len(df_filtered)} 条")

        return df_filtered

    def _convert_period(self, price_data: PriceData, period: str, market_code: MarketCode) -> PriceData:
        """周期转换（日线→周线/月线）

        复用 BarAggregator 做核心聚合，保留 _filter_non_trading_periods
        过滤空周期（整周/月都是节假日的场景）。

        Args:
            price_data: 日线数据（PriceData对象）
            period: 目标周期 ('weekly' 或 'monthly')
            market_code: 市场代码（用于交易日历判断）

        Returns:
            转换后的 PriceData 对象
        """
        if period == 'daily' or price_data.count == 0:
            return price_data

        # PriceData -> DataFrame，对齐为事实标准列名
        df = price_data.to_dataframe()
        df = df.rename(columns={'date': 'trade_date'})
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        # BarAggregator 需要 amount 列；旧数据可能没有，用 0 填充
        if 'amount' not in df.columns:
            df['amount'] = 0.0

        # 使用 BarAggregator 做核心聚合
        aggregator = BarAggregator()
        if period == 'weekly':
            df_copy = aggregator.daily_to_weekly(df)
        elif period == 'monthly':
            df_copy = aggregator.daily_to_monthly(df)
        else:
            logger.warning(f"[Adapter] 不支持的周期类型: {period}，返回原始数据")
            return price_data

        # 保留旧代码的空周期过滤（整周/月都是节假日的场景）
        df_copy = df_copy.rename(columns={'trade_date': 'date'})
        df_copy = self._filter_non_trading_periods(df_copy, period, market_code)

        # 类型安全检查
        if 'date' in df_copy.columns:
            df_copy['date'] = pd.to_datetime(df_copy['date'])
            if not pd.api.types.is_datetime64_any_dtype(df_copy['date']):
                raise TypeError(f"_convert_period: date 列转换后类型不正确: {df_copy['date'].dtype}")

        # 转换回 PriceData 强类型
        records = []
        for _, row in df_copy.iterrows():
            records.append(
                OHLCVRecord(
                    date=pd.Timestamp(row['date']),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                    turnover_rate=float(row['turnover_rate']) if 'turnover_rate' in df_copy.columns and pd.notna(row.get('turnover_rate')) else None,
                )
            )

        return PriceData(
            records=records,
            symbol=price_data.symbol,
            start_date=records[0].date if records else price_data.start_date,
            end_date=records[-1].date if records else price_data.end_date,
            count=len(records)
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
            'turnover_rate': quote.turnover_rate,
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
