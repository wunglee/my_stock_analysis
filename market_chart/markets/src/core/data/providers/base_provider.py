"""  
Provider 基类 - 数据提供者封装

核心职责:
- 对外提供统一的数据接口
- 封装缓存管理器，自动处理缓存读写
- 子类实现具体的 API 调用逻辑

使用示例:
    provider = AKShareDataProvider()
    price_data = provider.get_index_prices(
        symbol='000300.SH',
        start_date='2025-01-01',
        end_date='2025-01-31',
        current_time=pd.Timestamp.now()
    )
"""
import logging
import time
from abc import abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
import pandas as pd

from core.data.providers.protocols import PriceData, HistoricalDataProvider, TickRange, IntradayData
from core.share.config_manager import ConfigManager
from core.share.market import MarketUtils
from core.share.market.data_types import OHLCVRecord
from core.share.market.market_enums import TradingPhase, MarketCode
from core.share.market.market_time_utils import MarketTimeUtils

logger = logging.getLogger('BaseDataProvider')


class BaseDataProvider(HistoricalDataProvider):
    """
    数据提供者基类（封装缓存管理）
    
    核心职责:
    1. 对外提供统一的数据接口
    2. 封装缓存管理器，自动处理缓存读写
    3. 子类实现具体的 API 调用逻辑
    
    子类必须实现:
    - _fetch_from_external_api(symbol, start_date, end_date, period) -> PriceData
    - get_intraday_data(symbol, tick_range, market_local_time) -> IntradayData
    - 其他 HistoricalDataProvider 的抽象方法
    """

    def __init__(self, caching_provider=None):
        """初始化数据提供者

        Args:
            caching_provider: 可选的 CachingDataProvider 实例（方案B）。
                              提供时优先使用方案B的磁盘缓存+自动补全链路；
                              不提供时回退到方案C的 ThreeLayerCacheManager。
        """
        if caching_provider is not None:
            # 方案B：使用 CachingDataProvider（磁盘缓存优先 + 自动补全）
            self._caching_provider = caching_provider
            self._cache_manager = None
        else:
            # 方案C（回退）：使用 ThreeLayerCacheManager
            from infrastructure.cache import create_cache_manager
            self._cache_manager = create_cache_manager()
            self._caching_provider = None

        self.config_manager = ConfigManager()
        self._enable_memory_cache = True  # 启用分时数据内存缓存
        self._memory_cache = {}  # 分时数据缓存字典

    def _get_with_cache(self,
                        symbol: str,
                        start_date: pd.Timestamp,
                        end_date: pd.Timestamp,
                        market_local_time: pd.Timestamp,
                        period: str = 'daily'):
        """
        带缓存的数据获取（核心方法）

        优先走方案B（CachingDataProvider 磁盘缓存+自动补全），
        不提供时回退到方案C（ThreeLayerCacheManager 三层缓存）。

        Args:
            symbol: 指数代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            market_local_time: 目标市场当前本地时间（必须带市场时区信息）
            period: 数据粒度 ('daily'/'weekly'/'monthly'，传给API，默认 daily)

        Returns:
            PriceData 对象
        """
        logger.debug(f"📋 带缓存查询: {symbol}, {start_date} ~ {end_date}, period={period}")

        # 确保市场本地时间带有正确的时区
        market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, symbol)

        if self._caching_provider is not None:
            # 方案B：使用 CachingDataProvider（磁盘缓存优先 + 自动补全）
            result_df = self._get_from_caching_provider(symbol, start_date, end_date, period)
        else:
            # 方案C（回退）：使用 ThreeLayerCacheManager
            result_df = self._cache_manager.get_data(
                symbol=symbol,
                from_date=start_date,
                to_date=end_date,
                period=period,
                db_fetch_func=None,
                api_fetch_func=lambda s, e, period: self._fetch_from_external_api(symbol, s, e, period),
                current_time=market_local_time
            )

        # 转换为 PriceData
        if result_df is not None and not result_df.empty:
            price_data = PriceData.from_dataframe(result_df, symbol)
            logger.info(f"✅ 返回数据: {len(result_df)} 条")
        else:
            # 返回空 PriceData
            price_data = PriceData(
                records=[],
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                count=0
            )
            logger.warning(f"⚠️ 所有缓存都无数据: {symbol} {start_date}~{end_date}")

        # 设置 needs_realtime_kline 标记
        if price_data and price_data.count > 0:
            self.set_needs_realtime_kline(price_data, market_local_time)
            logger.debug(f"✅ needs_realtime_kline已设置为: {price_data.needs_realtime_kline}")

        return price_data

    def _get_from_caching_provider(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str
    ) -> pd.DataFrame | None:
        """通过 CachingDataProvider（方案B）获取数据，返回 market_chart 兼容的 DataFrame

        方案B 内部已完成：磁盘缓存查询 → 缺失区间检测 → 外部数据源补全（带超时保护）→ 自动保存。
        此方法仅负责周期路由和列名转换（trade_date → date，移除 symbol 列）。
        """
        if period == 'weekly':
            df = self._caching_provider.get_weekly_bars(symbol, start_date, end_date)
        elif period == 'monthly':
            df = self._caching_provider.get_monthly_bars(symbol, start_date, end_date)
        else:
            df = self._caching_provider.get_daily_bars(symbol, start_date, end_date)

        if df is None or df.empty:
            return None

        df = df.copy()
        if 'trade_date' in df.columns:
            df = df.rename(columns={'trade_date': 'date'})
        if 'symbol' in df.columns:
            df = df.drop(columns=['symbol'])
        return df

    def _fetch_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str) -> \
    Optional[
        pd.DataFrame]:
        """
        从 API 获取数据（为缓存管理器提供回调）

        统一策略：fetcher 永远只取日线，周期转换在数据层完成并缓存。
        这样无论哪个 fetcher 被动态选中，周/月线行为一致且都走缓存。

        Args:
            symbol: 指数代码
            start_date: 开始日期
            end_date: 结束日期
            period: 周期

        Returns:
            DataFrame 或 None
        """
        try:
            result = self._fetch_history_kline_from_external_api(symbol, start_date, end_date, 'daily')

            # 归一化到 DataFrame
            if isinstance(result, pd.DataFrame):
                df = result
            elif result and hasattr(result, 'count') and result.count > 0:
                df = result.to_dataframe()
            else:
                return None

            if df.empty:
                return None

            # 数据层统一周期转换
            if period != 'daily':
                from core.share.market import MarketUtils
                market_code = MarketUtils.infer_market_from_symbol(symbol)
                df = self._convert_period(df, period, market_code)

            return df if not df.empty else None
        except Exception as e:
            logger.error(f"❌ API查询失败: {symbol} {start_date}~{end_date}, error={e}")

        return None

    def set_needs_realtime_kline(self, price_data: PriceData, market_local_time: pd.Timestamp):
        """设置 needs_realtime_kline 标记
        
        根据当前交易时段判断是否需要获取实时K线：
        - 盘前/盘中/午盘：需要获取实时K线（True）
        - 盘后：不需要（False，当天K柱已在历史数据中）
        
        Args:
            price_data: 价格数据对象
            market_local_time: 市场本地时间（必须带正确的市场时区，由API层传入）
        """
        from core.share.market.market_time_utils import MarketTimeUtils

        market_code = MarketUtils.infer_market_from_symbol(price_data.symbol)
        # 确保时间戳带有正确的市场时区
        market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, price_data.symbol)
        trading_phase = MarketTimeUtils.determine_trading_phase(market_code, market_local_time)

        # 🔧 直接修改 price_data 对象的属性
        price_data.needs_realtime_kline = trading_phase in [
            TradingPhase.BEFORE_OPEN,
            TradingPhase.TRADING,
            TradingPhase.NOON_BREAK
        ]

    def merge_realtime_kline_to_period(self,
                                       price_data: PriceData,
                                       realtime_kline: dict,
                                       period: str) -> PriceData:
        """将实时K线数据合并到周线/月线K线数据中
        
        逻辑：
        1. 日线（daily）：不需要合并，实时K线作为独立的当天K柱
        2. 周线（weekly）：
           - 如果当天是新周的第一天：实时K线作为新的独立周K柱
           - 如果当天不是新周的第一天：实时K线叠加到最后一个周K柱上
        3. 月线（monthly）：
           - 如果当天是新月的第一天：实时K线作为新的独立月K柱
           - 如果当天不是新月的第一天：实时K线叠加到最后一个月K柱上
        
        Args:
            price_data: 历史K线数据（PriceData对象）
            realtime_kline: 实时K线数据字典 {'date', 'open', 'high', 'low', 'close', 'volume'}
            period: 数据粒度 ('daily'/'weekly'/'monthly')
        
        Returns:
            合并后的 PriceData 对象
        """
        from core.share.market.data_types import OHLCVRecord
        import copy

        # 日线不需要合并，直接返回原数据（实时K线由前端独立处理）
        if period == 'daily':
            return price_data

        # 如果没有历史数据或实时K线数据无效，直接返回原数据
        if not price_data or price_data.count == 0 or not realtime_kline or not realtime_kline.get('date'):
            return price_data

        # 解析实时K线的日期
        realtime_date = pd.Timestamp(realtime_kline['date'])

        # 获取最后一个历史K柱的日期
        last_record = price_data.records[-1]
        last_date = last_record.date

        # 判断是否需要创建新K柱还是合并到最后一个K柱
        should_create_new_bar = False

        if period == 'weekly':
            # 周线：判断realtime_date和last_date是否在同一周
            # 使用ISO周历（周一为一周的开始）
            realtime_week = realtime_date.isocalendar()[1]  # (year, week, weekday)
            realtime_year = realtime_date.isocalendar()[0]
            last_week = last_date.isocalendar()[1]
            last_year = last_date.isocalendar()[0]

            # 如果年份或周数不同，说明是新周，需要创建新K柱
            should_create_new_bar = (realtime_year != last_year) or (realtime_week != last_week)

        elif period == 'monthly':
            # 月线：判断realtime_date和last_date是否在同一月
            should_create_new_bar = (realtime_date.year != last_date.year) or (realtime_date.month != last_date.month)

        # 深拷贝一份records，避免修改原数据
        new_records = copy.deepcopy(price_data.records)

        if should_create_new_bar:
            # 创建新的独立K柱
            logger.info(f"🔄 {period}线 - 创建新K柱: {realtime_date.strftime('%Y-%m-%d')}")
            new_record = OHLCVRecord(
                date=realtime_date,
                open=float(realtime_kline.get('open', 0)),
                high=float(realtime_kline.get('high', 0)),
                low=float(realtime_kline.get('low', 0)),
                close=float(realtime_kline.get('close', 0)),
                volume=float(realtime_kline.get('volume', 0))
            )
            new_records.append(new_record)
        else:
            # 合并到最后一个K柱
            logger.info(
                f"🔄 {period}线 - 合并到最后K柱: {last_date.strftime('%Y-%m-%d')} <- {realtime_date.strftime('%Y-%m-%d')}")
            last_record_copy = copy.copy(new_records[-1])

            # 合并逻辑：
            # - open: 保持周期开始时的开盘价（不变）
            # - high: 取max(历史high, 实时high)
            # - low: 取min(历史low, 实时low)
            # - close: 使用实时close（最新收盘价）
            # - volume: 累加（但实时volume已包含当天所有成交量，所以直接使用）
            new_records[-1] = OHLCVRecord(
                date=last_record_copy.date,  # 保持周期开始日期
                open=last_record_copy.open,  # 保持周期开盘价
                high=max(last_record_copy.high, float(realtime_kline.get('high', 0))),
                low=min(last_record_copy.low, float(realtime_kline.get('low', 0))),
                close=float(realtime_kline.get('close', 0)),  # 使用最新收盘价
                volume=last_record_copy.volume + float(realtime_kline.get('volume', 0))  # 累加成交量
            )

        # 创建新的 PriceData 对象
        return PriceData(
            records=new_records,
            symbol=price_data.symbol,
            start_date=new_records[0].date if new_records else price_data.start_date,
            end_date=new_records[-1].date if new_records else price_data.end_date,
            count=len(new_records)
        )

    # ========================================================================
    # 数据获取接口（对外提供，自动使用缓存）
    # ========================================================================

    def get_index_prices(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp,
                         market_local_time: pd.Timestamp, period: str = 'daily'):
        """
        获取指数价格数据（对外接口，自动使用缓存）
        
        Args:
            symbol: 指数代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            market_local_time: 目标市场当前本地时间（必须带市场时区信息）
            period: 数据粒度 ('daily'/'weekly'/'monthly'，默认 daily)
        
        Returns:
            PriceData: 价格数据对象
        """
        return self._get_with_cache(symbol, start_date, end_date, market_local_time, period)

    def get_stock_prices(self, stock_id: str, start_date: pd.Timestamp, end_date: pd.Timestamp,
                         market_local_time: pd.Timestamp, period: str = 'daily'):
        """
        获取股票价格数据（对外接口，自动使用缓存）
        
        Args:
            stock_id: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            market_local_time: 目标市场当前本地时间（必须带市场时区信息）
            period: 数据粒度 ('daily'/'weekly'/'monthly'，默认 daily)
        
        Returns:
            PriceData: 价格数据对象
        """
        return self._get_with_cache(stock_id, start_date, end_date, market_local_time, period)

    def get_index_returns(self, symbol: str,
                          start_date: pd.Timestamp,
                          end_date: pd.Timestamp) -> pd.Series:
        """
        获取指数收益率序列（通用实现）
        
        此方法在 BaseDataProvider 中实现，所有子类自动继承
        从 get_index_prices 获取价格数据并计算收益率
        自动获取当前市场时间并确保时区正确
        
        Args:
            symbol: 指数代码
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            pd.Series: 收益率序列，以日期为索引
        """
        # 获取价格数据
        from core.share.market.market_time_utils import MarketTimeUtils

        market_local_time = MarketTimeUtils.get_market_time_now(symbol)
        # 确保市场本地时间带有正确的时区
        market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, symbol)
        price_data = self.get_index_prices(symbol, start_date, end_date, market_local_time)

        if not price_data or price_data.count == 0:
            return pd.Series(dtype=float)

        # 转换为 DataFrame 并计算收益率
        df = price_data.to_dataframe()
        df = df.set_index('date')
        returns = df['close'].pct_change().dropna()

        return returns

    def get_intraday_data(
            self, symbol: str, tick_range: TickRange = None,
            market_local_time: pd.Timestamp = None) -> IntradayData:
        """
        获取分时数据（日内Tick数据）

        策略：
        1. 集合竞价时段（9:00-9:30）：返回空数据用于清空分时图 + 实时盘口
        2. 交易时段（上午或下午）：返回当前时刻之前的数据 + 实时盘口
        3. 午盘休市时段（11:30-13:00）：返回上午的分时数据 + 最后的盘口
        4. 盘后时段（15:00之后）：返回当天的全天分时数据（无盘口）
        5. 最后返回空数据

        Args:
            symbol: 证券代码
            tick_range: 时间范围
            market_local_time: 目标市场当前本地时间（必须带市场时区信息）
                              如果为None，自动使用 MarketTimeUtils.get_market_time_now(symbol) 获取

        Returns:
            IntradayData: 完整的分时数据对象

        注意：
        - 此方法只负责获取真实数据
        - 模拟数据由 MockDataProvider 单独处理
        """

        logger.info(f"获取真实分时数据: symbol={symbol}")

        # 🔧 根据symbol识别市场
        market_code = MarketUtils.infer_market_from_symbol(symbol)
        logger.info(f"识别市场: {symbol} -> {market_code.value}")

        # 如果没有提供 market_local_time，使用 MarketTimeUtils.get_market_time_now 获取
        if market_local_time is None:
            market_local_time = MarketTimeUtils.get_market_time_now(symbol)
            logger.info(f"自动获取市场当前时间: {market_local_time}")
        # 确保 market_local_time 带有正确的市场时区
        market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, symbol)

        trade_date = market_local_time.normalize()

        intraday_data = None
        trading_phase = MarketTimeUtils.determine_trading_phase(market_code, market_local_time)
        trading_hours = self.config_manager.get_trading_hours(market_code.value)
        if trading_phase == TradingPhase.BEFORE_OPEN:
            # 集合竞价时段（9:00-9:30）：返回空数据，用于清空分时图
            logger.info(f"集合竞价时段（{market_code.value}），返回空数据用于清空分时图")
            intraday_data = self._build_empty_intraday_data(market_local_time, symbol, trading_phase)
        elif trading_phase == TradingPhase.AFTER_CLOSE:
            last_trade_date = MarketTimeUtils.get_last_trade_date(market_code, market_local_time)
            last_trade_date_cache_key = f"intraday_{symbol}_{last_trade_date.strftime('%Y-%m-%d')}_AFTER_CLOSE"
            if self._enable_memory_cache:
                date_cache = self._get_from_memory_cache(last_trade_date_cache_key)
                intraday_data = IntradayData.from_any(date_cache)
            if intraday_data is None:
                # 🔧 尝试从外部获取last_trade_date的分时数据
                logger.info(f"尝试直接从外部获取最后交易日的数据: {last_trade_date}")
                try:
                    start_time_str, end_time_str = self._get_range_start_end_string(symbol, tick_range, last_trade_date)
                    # 获取原始DataFrame
                    df = self._fetch_real_intraday_from_external_api(symbol, start_time_str, end_time_str)
                    if df is not None and not df.empty:
                        # 构建 IntradayData（盘后不获取实时盘口）
                        intraday_data = self._build_intraday_data(
                            df, symbol, last_trade_date,
                            fetch_trade_records=False, should_poll=False
                        )
                        # 缓存数据（如果需要）
                        if self._enable_memory_cache:
                            self._set_to_memory_cache_obj(last_trade_date_cache_key, intraday_data)
                            logger.info(f"✅ 数据已缓存: {last_trade_date_cache_key}")
                except Exception as e:
                    # 其他异常（如网络错误、API错误），记录警告并fallback
                    logger.warning(f"获取最后交易日的真实分时数据失败: {e}")
            else:
                logger.info(f"✅ 盘后缓存命中（来自最后盘中数据）: {last_trade_date_cache_key}")
        elif trading_phase == TradingPhase.NOON_BREAK:
            # 午盘休市时段（11:30-13:00）：返回上午的分时数据 + 最后的盘口
            logger.info(f"午盘休市时段（{market_code.value}），返回上午数据 + 盘口")

            # 构建上午时间范围（9:30-11:30）
            morning_start = trading_hours['open']  # 09:30
            morning_end = trading_hours['lunch_start']  # 11:30
            if tick_range is None:
                tick_range = TickRange(
                    start_time=pd.Timestamp(f"{trade_date} {morning_start}"),
                    end_time=pd.Timestamp(f"{trade_date} {morning_end}"),
                )
            # 获取上午的分时数据
            start_time_str, end_time_str = self._get_range_start_end_string(symbol, tick_range, trade_date)
            df = self._fetch_real_intraday_from_external_api(symbol, start_time_str,end_time_str)

            # 构建 IntradayData（午休时段获取上午收盘时的盘口）
            intraday_data = self._build_intraday_data(
                df, symbol, trade_date,
                fetch_trade_records=True, should_poll=False
            )

        elif trading_phase == TradingPhase.TRADING:
            # 交易时段（上午或下午）：返回当前时刻之前的数据 + 实时盘口
            logger.info(f"交易时段（{trading_phase.value}），返回实时数据 + 盘口")

            # 🔧 关键：盘中必须有tick_range，如果前端未提供，则自动创建（开盘到当前时刻）
            if tick_range is None:
                # 创建从开盘到当前时刻的tick_range
                tick_range = TickRange(
                    start_time=pd.Timestamp(f"{trade_date} {trading_hours['open']}"),
                    end_time=market_local_time,  # 使用不带时区的本地时间
                    period_seconds=5
                )
                logger.info(f"📅 自动创建 TickRange（盘中首次加载）: {tick_range.start_time} ~ {tick_range.end_time}")

            # 🔧 尝试获取真实数据（盘中不使用缓存，实时获取）
            logger.info(f"📊 真实数据模式 - 从外部数据源获取 (phase={trading_phase.value})")
            try:
                start_time_str, end_time_str = self._get_range_start_end_string(symbol, tick_range, trade_date)
                # 获取原始DataFrame（传入current_time用于判断时间范围）
                df = self._fetch_real_intraday_from_external_api(symbol, start_time_str, end_time_str)
                if df is not None:
                    if tick_range is None:
                        # 一个完整交易日应该有270分钟的数据（09:30-12:00 = 150分钟，13:00-15:00 = 120分钟）
                        expected_ticks = 270
                        actual_ticks = len(df)

                        logger.info(f"✅ 返回 {actual_ticks} 条分时数据（期望 {expected_ticks} 条）")

                        # 🔧 严格模式：如果是盘后且数据不完整（少于80%），抛出异常
                        # 盘后应该返回完整的交易日数据，如果不完整说明数据源有问题
                        if actual_ticks < expected_ticks * 0.8:
                            error_msg = f"盘后数据不完整：期望{expected_ticks}条，实际仅获取{actual_ticks}条。可能原因：API限制或数据源问题。"
                            logger.error(f"❌ {error_msg}")
                            raise ValueError(error_msg)
                    else:
                        # 构建 IntradayData（交易时段获取实时盘口）
                        intraday_data = self._build_intraday_data(
                            df, symbol, trade_date,
                            fetch_trade_records=True, should_poll=True
                        )
                else:
                    intraday_data = None
            except Exception as e:
                # 其他异常（如网络错误、API错误），记录详细错误
                logger.error(f"🔴 获取真实分时数据失败: {e}", exc_info=True)
                intraday_data = None

        # 如果所有尝试都失败了，抛出异常
        if intraday_data is None:
            error_msg = f"无法获取分时数据: symbol={symbol}, date={trade_date}, phase={trading_phase.value}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        return intraday_data

    def _build_intraday_data(self, df, symbol: str, trade_date: pd.Timestamp,
                             fetch_trade_records: bool = True, should_poll: bool = True) -> IntradayData:
        """
        构建 IntradayData 对象（统一处理盘口获取和数据转换）

        Args:
            df: 返回的 DataFrame
            symbol: 证券代码
            trade_date: 交易日期
            fetch_trade_records: 是否获取盘口数据


        Returns:
            IntradayData 对象
        """

        # 使用 IntradayData 的类方法转换 DataFrame
        intraday_data = self._to_IntradayData(
            df, symbol, trade_date,
            interpolate_func=self._interpolate_to_5_seconds
        )
        # 获取盘口和成交明细
        if fetch_trade_records:
            order_book_bids, order_book_asks, trade_records, order_book_message, trade_records_message = \
                self.get_order_book_and_trades(symbol)
            # 设置盘口和成交明细
            intraday_data.order_book_bids = order_book_bids
            intraday_data.order_book_asks = order_book_asks
            intraday_data.trade_records = trade_records
            intraday_data.order_book_message = order_book_message
            intraday_data.trade_records_message = trade_records_message
        intraday_data.should_poll = should_poll
        return intraday_data

    def _build_empty_intraday_data(self, market_local_time, symbol, trading_phase):
        import pandas as pd
        # 🔧 使用文件顶部的全局导入
        empty_df = pd.DataFrame(columns=[
            '时间', '开盘', '收盘', '最高', '最低',
            '成交量', '成交额', '振幅', '涨跌幅', '涨跌额', '换手率'
        ])
        # 构建 IntradayData（集合竞价时段也要尝试获取盘口）
        intraday_data = self._build_intraday_data(
            empty_df, symbol, trade_date=market_local_time,
            fetch_trade_records=True, should_poll=(trading_phase != TradingPhase.AFTER_CLOSE)
        )
        return intraday_data

    def _get_range_start_end_string(self, symbol, tick_range, trade_date):
        # 构建查询时间范围
        if tick_range is not None:
            # 如果提供了 tick_range，使用其时间范围（增量获取或盘中首次加载）
            start_time = tick_range.start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_time = tick_range.end_time.strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"使用tick_range时间范围: {start_time} ~ {end_time}")
        else:
            # tick_range=None：盘后获取全天数据
            # 使用文件顶部的全局导入
            # 获取市场代码
            market_code = MarketUtils.infer_market_from_symbol(symbol)
            trading_hours = self.config_manager.get_trading_hours(market_code.value)
            # 构建全天时间范围（从开盘到收盘）
            morning_start = trading_hours['open']
            afternoon_end = trading_hours['close']

            start_time = f"{trade_date.date()} {morning_start}"
            end_time = f"{trade_date.date()} {afternoon_end}"
            logger.info(f"📅 盘后模式，使用市场{market_code.value}的全天范围: {start_time} ~ {end_time}")
        return start_time, end_time

    def _interpolate_to_5_seconds(self, ticks: list) -> list:
        """
        处理1分钟粒度的tick数据

        🔧 修改：直接返回原始数据，不做插值（1分钟数据已经足够）

        Args:
            ticks: 原始1分钟粒度的tick列表

        Returns:
            原始 tick 列表（不再插值）
        """
        # 直接返回原始数据，不做插值
        return ticks

    def _filter_non_trading_periods(self, df: pd.DataFrame, period: str, market_code: MarketCode) -> pd.DataFrame:
        """过滤非交易周期
        
        智能过滤空周期：只过滤"非交易周/月"（整周/月都是节假日），
        保留"有交易但无数据的周/月"（用于判断上市周）
        
        Args:
            df: 重采样后的 DataFrame（已 reset_index）
            period: 周期类型 ('weekly' 或 'monthly')
            market_code: 市场代码
        
        Returns:
            过滤后的 DataFrame
        """
        from core.share.market.trading_calendar_service import TradingCalendarService

        calendar_service = TradingCalendarService()
        original_count = len(df)
        rows_to_keep = []
        rows_filtered = []

        for idx, row in df.iterrows():
            is_empty = pd.isna(row['open']) and pd.isna(row['high']) and pd.isna(row['low']) and pd.isna(row['close'])

            if is_empty:
                # 空行：需要判断是否是非交易周期
                date = pd.Timestamp(row['date'])

                if period == 'weekly':
                    # 获取该周的周一和周日
                    week_start = date - pd.Timedelta(days=date.weekday())
                    week_end = week_start + pd.Timedelta(days=6)
                    period_start, period_end = week_start, week_end
                    period_name = '非交易周'

                elif period == 'monthly':
                    # 获取该月的第一天和最后一天
                    month_start = date.replace(day=1)
                    if date.month == 12:
                        month_end = pd.Timestamp(date.year + 1, 1, 1) - pd.Timedelta(days=1)
                    else:
                        month_end = pd.Timestamp(date.year, date.month + 1, 1) - pd.Timedelta(days=1)
                    period_start, period_end = month_start, month_end
                    period_name = '非交易月'
                else:
                    # 不支持的周期，保留
                    rows_to_keep.append(idx)
                    continue

                # 检查这个周期是否有任何交易日
                has_trading_day = False
                current_date = period_start
                while current_date <= period_end:
                    if calendar_service.is_trading_day(market_code, current_date):
                        has_trading_day = True
                        break
                    current_date += pd.Timedelta(days=1)

                if has_trading_day:
                    # 有交易但无数据：保留（可能是上市前）
                    rows_to_keep.append(idx)
                else:
                    # 整周/月无交易：过滤
                    rows_filtered.append((idx, date, period_name))
            else:
                # 非空行：保留
                rows_to_keep.append(idx)

        # 应用过滤
        df_filtered = df.loc[rows_to_keep]

        # 记录过滤信息
        if rows_filtered:
            logger.info(f"🧹 {period}线转换：过滤了 {len(rows_filtered)} 个非交易周期")
            for idx, date, reason in rows_filtered[:5]:  # 只显示前5个
                logger.info(f"   - {date.strftime('%Y-%m-%d')}: {reason}")
            if len(rows_filtered) > 5:
                logger.info(f"   ... 还有 {len(rows_filtered) - 5} 个")
            logger.info(f"   原始{period}线数据: {original_count} 条 → 过滤后: {len(df_filtered)} 条")

        return df_filtered

    def _convert_period(self, df: 'pd.DataFrame', period: str, market_code: MarketCode) -> 'pd.DataFrame':
        """日线 DataFrame → 周线/月线 DataFrame

        纯数据转换，不涉及 PriceData 类型。
        由 _fetch_from_external_api 统一调用，转换结果直接进入缓存层。

        Args:
            df: 日线 DataFrame（含 date/open/high/low/close/volume 列）
            period: 目标周期 ('weekly' 或 'monthly')
            market_code: 市场代码（用于交易日历判断）

        Returns:
            转换后的 DataFrame
        """
        import pandas as pd

        if period == 'daily':
            return df

        df['date'] = pd.to_datetime(df['date'])
        df_work = df.set_index('date')

        if period == 'weekly':
            df_work = df_work.resample('W-MON', label='left', closed='left').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            df_work = df_work.reset_index()
            df_work = self._filter_non_trading_periods(df_work, period, market_code)

        elif period == 'monthly':
            df_work = df_work.resample('ME').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            df_work = df_work.reset_index()
            df_work = self._filter_non_trading_periods(df_work, period, market_code)
        else:
            logger.warning(f"不支持的周期类型: {period}，返回原始数据")
            return df

        if 'date' in df_work.columns:
            df_work['date'] = pd.to_datetime(df_work['date'])
            if not pd.api.types.is_datetime64_any_dtype(df_work['date']):
                raise TypeError(f"_convert_period: date 列转换后类型不正确: {df_work['date'].dtype}")

        return df_work

    def get_realtime_kline(self, symbol, period, provider):
        # 🆕 步骤1: 获取实时K线数据（日线维度）
        realtime_kline = provider._get_today_k_column(symbol=symbol)
        # 🆕 步骤2: 如果是周线/月线，需要合并到历史数据
        if period in ['weekly', 'monthly']:
            # 2.1 从缓存读取最后一个周期K柱（由第一个接口缓存）
            cache_key = f"last_period_bar_{symbol}_{period}"
            last_period_bar = provider._get_from_memory_cache(cache_key)

            if last_period_bar:
                # 2.2 使用缓存的最后一个K柱进行合并
                date = MarketTimeUtils.to_market_time_by_symbol(pd.Timestamp(last_period_bar['date']), symbol)
                logger.info(f"💾 从缓存读取最后一个{period}K柱: date={date}")

                # 构造PriceData对象（只包含最后一个K柱）
                last_record = OHLCVRecord(
                    date=date,
                    open=last_period_bar['open'],
                    high=last_period_bar['high'],
                    low=last_period_bar['low'],
                    close=last_period_bar['close'],
                    volume=last_period_bar['volume']
                )

                price_data = PriceData(
                    records=[last_record],
                    symbol=symbol,
                    start_date=last_record.date,
                    end_date=last_record.date,
                    count=1
                )

                # 2.3 调用合并逻辑
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)
                merged_price_data = provider.merge_realtime_kline_to_period(
                    price_data=price_data,
                    realtime_kline=realtime_kline,
                    period=period,
                    market_local_time=market_local_time
                )

                # 2.4 提取最后一个K柱返回给前端
                last_record = merged_price_data.records[-1]
                result = {
                    'date': last_record.date.strftime('%Y-%m-%d'),
                    'open': float(last_record.open),
                    'high': float(last_record.high),
                    'low': float(last_record.low),
                    'close': float(last_record.close),
                    'volume': int(last_record.volume),
                    'should_poll': realtime_kline.get('should_poll', False)
                }
                logger.info(
                    f"🔄 {period}线 - 使用缓存合并后返回: date={result['date']}, open={result['open']:.2f}, close={result['close']:.2f}")
            else:
                # 缓存中没有，需要查询历史数据（fallback机制）
                logger.warning(f"⚠️ {period}线 - 缓存未命中，需要查询历史数据")
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)
                end_date = market_local_time
                start_date = end_date - pd.Timedelta(days=90)

                price_data: PriceData = provider.get_index_prices(
                    symbol,
                    start_date,
                    end_date,
                    market_local_time,
                    period
                )

                if price_data and price_data.count > 0:
                    merged_price_data = provider.merge_realtime_kline_to_period(
                        price_data=price_data,
                        realtime_kline=realtime_kline,
                        period=period,
                        market_local_time=market_local_time
                    )

                    last_record = merged_price_data.records[-1]
                    result = {
                        'date': last_record.date.strftime('%Y-%m-%d'),
                        'open': float(last_record.open),
                        'high': float(last_record.high),
                        'low': float(last_record.low),
                        'close': float(last_record.close),
                        'volume': int(last_record.volume),
                        'should_poll': realtime_kline.get('should_poll', False)
                    }
                    logger.info(
                        f"🔄 {period}线 - fallback合并后返回: date={result['date']}, open={result['open']:.2f}, close={result['close']:.2f}")
                else:
                    # 没有历史数据时，返回原始实时数据
                    result = realtime_kline
                    logger.warning(f"⚠️ {period}线 - 无历史数据，返回原始实时K线")
        else:
            # 日线：直接返回实时K线
            result = realtime_kline
        return result

    def _get_today_k_column(self, symbol: str, market_local_time: pd.Timestamp = None) -> dict:
        """
        获取实时K线数据（当日K柱）

        Args:
            symbol: 证券代码

        Returns:
            dict: K线数据字典，格式：
            {
                'date': str,  # '2024-01-15'
                'open': float,  # 开盘价
                'high': float,  # 最高价
                'low': float,   # 最低价
                'close': float, # 收盘价（当前价）
                'volume': int,  # 成交量
                'trading_phase': str,  # 交易时段：before_open, trading, AFTER_CLOSE等
                'should_poll': bool  # 服务器根据 trading_phase 决定，前端只依赖此字段控制行为
            }
        """
        # 初始化返回数据（使用类型注解避免类型推断错误）
        from typing import Any, Dict
        kline_data: Dict[str, Any] = {
            'date': None,
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'volume': 0,
            'trading_phase': None,
            'should_poll': False
        }

        market_code = MarketUtils.infer_market_from_symbol(symbol)

        if not market_local_time:
            market_local_time = MarketTimeUtils.get_market_time_now(market_code)

        # 确保 market_local_time 带有正确的市场时区
        market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, symbol)
        trading_phase = MarketTimeUtils.determine_trading_phase(market_code, market_local_time)

        # 获取市场本地日期作为交易日
        trade_date = market_local_time.normalize()
        cache_key = f"realtime_kline_{symbol}_{trade_date.strftime('%Y-%m-%d')}"

        if trading_phase == TradingPhase.TRADING:
            # 盘中时段：获取实时K线数据
            try:
                # 1. 尝试从缓存获取
                cached = self._get_from_memory_cache(cache_key)

                # 2. 如果无缓存，从分时数据初始化
                if not cached:
                    intraday_data = self.get_intraday_data(symbol)
                    if intraday_data.ticks and len(intraday_data.ticks) > 0:
                        prices = [tick.price for tick in intraday_data.ticks]
                        volumes = [tick.volume for tick in intraday_data.ticks]

                        cached = {
                            'date': trade_date.strftime('%Y-%m-%d'),
                            'open': prices[0],
                            'high': max(prices),
                            'low': min(prices),
                            'close': prices[-1],
                            'volume': sum(volumes),
                            'trading_phase': trading_phase.name,
                            'should_poll': True
                        }
                        self._set_to_memory_cache_obj(cache_key, cached)
                    else:
                        # 分时数据为空时返回空K线
                        kline_data['date'] = trade_date.strftime('%Y-%m-%d')
                        kline_data['trading_phase'] = trading_phase.name
                        kline_data['should_poll'] = True
                        return kline_data

                # 3. 获取最新分钟数据更新K线
                try:
                    df = self._fetch_today_k_column_from_external_api(market_local_time, symbol)

                    if df is not None and not df.empty:
                        # 更新高低点和收盘价
                        latest_high = float(df['最高'].iloc[-1])
                        latest_low = float(df['最低'].iloc[-1])
                        latest_close = float(df['收盘'].iloc[-1])
                        latest_volume = int(df['成交量'].iloc[-1])

                        kline_data = {
                            'date': trade_date.strftime('%Y-%m-%d'),
                            'open': cached['open'],  # 开盘价不变
                            'high': max(cached['high'], latest_high),
                            'low': min(cached['low'], latest_low),
                            'close': latest_close,
                            'volume': cached['volume'] + latest_volume,
                            'trading_phase': trading_phase.name,
                            'should_poll': True
                        }

                        # 更新缓存
                        self._set_to_memory_cache_obj(cache_key, kline_data)
                    else:
                        # 无数据时使用缓存
                        kline_data = cached.copy()
                        kline_data['trading_phase'] = trading_phase.name
                        kline_data['should_poll'] = True

                except Exception as e:
                    logger.warning(f"获取分钟数据失败: {e}，使用缓存数据")
                    # API失败时使用缓存
                    kline_data = cached.copy()
                    kline_data['trading_phase'] = trading_phase.name
                    kline_data['should_poll'] = True

            except Exception as e:
                logger.error(f"获取实时K线失败: {e}")
                kline_data['date'] = trade_date.strftime('%Y-%m-%d')
                kline_data['trading_phase'] = trading_phase.name
                kline_data['should_poll'] = True

        elif trading_phase == TradingPhase.BEFORE_OPEN:
            # 盘前时段：使用集合竞价价格（从盘口获取）
            try:
                order_book_bids, order_book_asks = self._fetch_realtime_order_book_from_external_api(symbol)
                auction_price = None

                if order_book_bids and len(order_book_bids) > 0:
                    # 使用买一价作为集合竞价参考价格
                    auction_price = order_book_bids[0].price

                kline_data = {
                    'date': trade_date.strftime('%Y-%m-%d'),
                    'open': auction_price,
                    'high': auction_price,
                    'low': auction_price,
                    'close': auction_price,
                    'volume': 0,
                    'trading_phase': trading_phase.name,
                    'should_poll': True
                }
            except Exception as e:
                logger.error(f"获取集合竞价价格失败: {e}")
                kline_data['date'] = trade_date.strftime('%Y-%m-%d')
                kline_data['trading_phase'] = trading_phase.name
                kline_data['should_poll'] = True

        # 其他时段（AFTER_CLOSE等）返回默认数据，不轮询
        kline_data['trading_phase'] = trading_phase.name
        return kline_data

    def get_order_book_and_trades(self, symbol: str) -> tuple:
        """
        获取盘口和成交明细数据（仅限个股）

        Args:
            symbol: 证券代码

        Returns:
            (order_book_bids, order_book_asks, trade_records, order_book_message, trade_records_message)
        """

        order_book_bids = []
        order_book_asks = []
        trade_records = []
        order_book_message = ''
        trade_records_message = ''

        # 指数不获取盘口和成交明细
        if MarketUtils.is_index(symbol):
            order_book_message = '指数无盘口数据'
            trade_records_message = '指数无成交明细'
            return order_book_bids, order_book_asks, trade_records, order_book_message, trade_records_message

        # 获取实时盘口数据
        try:
            order_book_bids, order_book_asks = self._fetch_realtime_order_book_from_external_api(symbol)
            if not order_book_bids and not order_book_asks:
                order_book_message = '无法获取盘口数据'
            logger.info(f"✅ 获取实时盘口: {len(order_book_bids)}个买盘, {len(order_book_asks)}个卖盘")
        except Exception as e:
            logger.warning(f"获取实时盘口失败: {e}")
            order_book_message = '无法获取盘口数据'

        # 获取实时成交明细
        try:
            trade_records = self._fetch_realtime_trade_records_from_external_api(symbol)
            if not trade_records:
                trade_records_message = '无法获取成交明细'
            logger.info(f"✅ 获取实时成交: {len(trade_records)}条")
        except Exception as e:
            logger.warning(f"获取实时成交明细失败: {e}")
            trade_records_message = '无法获取成交明细'

        return order_book_bids, order_book_asks, trade_records, order_book_message, trade_records_message

    def _set_to_memory_cache_obj(self, cache_key: str, obj: Any):
        """
        将任意对象写入内存缓存（专门用于IntradayData等非DataFrame对象）

        Args:
            cache_key: 缓存键
            obj: 任意对象
        """
        if not self._enable_memory_cache or obj is None:
            return
        import time
        self._memory_cache[cache_key] = {
            'data': obj,
            'timestamp': time.time()
        }
        logger.debug(f"✅ 写入内存缓存: {cache_key}")

    def _get_from_memory_cache(self, cache_key: str) -> Any:
        """
        从内存缓存读取对象

        Args:
            cache_key: 缓存键

        Returns:
            缓存的对象或None
        """
        if not self._enable_memory_cache:
            return None

        cached = self._memory_cache.get(cache_key)
        if cached:
            logger.debug(f"✅ 内存缓存命中: {cache_key}")
            return cached.get('data')

        return None

    def get_test_symbol(self) -> str:
        """
        获取测试符号（子类可重写）
        
        Returns:
            str: 测试用的股票/指数代码
        """
        return '^GSPC.US'  # 默认测试符号：标普500

    # ========================================================================
    # 配置管理接口（具体方法，基类统一实现）
    # ========================================================================

    @classmethod
    def _get_config_path(cls, filename: str) -> Path:
        """
        获取配置文件路径
        
        Args:
            filename: 配置文件名
            
        Returns:
            Path: 配置文件完整路径
            
        Note:
            使用 ConfigManager.get_config_path() 统一获取配置路径
        """
        from core.share.config_manager import ConfigManager
        config_manager = ConfigManager()
        # 使用 ConfigManager 的封装方法获取配置路径
        config_path_str = config_manager.get_config_path(filename.replace('.yml', ''))
        return Path(config_path_str)

    @classmethod
    def test_provider(cls, provider_id: str, credential: str) -> Dict[str, Any]:
        """
        测试数据源连接
        
        Args:
            provider_id: 数据源ID
            credential: 临时凭证（用于测试）
            
        Returns:
            测试结果字典
        """
        logger.info(f"Testing connection for provider: {provider_id}")

        try:
            # 获取数据源配置
            config_manager = ConfigManager()
            data_config = config_manager.get_provider_config()
            providers = data_config.providers

            provider_config = next((p for p in providers if p.get('id') == provider_id or p.get('name') == provider_id),
                                   None)

            if not provider_config:
                return {
                    'status': 'error',
                    'test_result': 'failed',
                    'available': False,
                    'message': f'数据源不存在: {provider_id}',
                    'error_code': 'PROVIDER_NOT_FOUND'
                }

            # 动态创建适配器实例
            adapter_module = provider_config.get('adapter_module')
            adapter_class = provider_config.get('adapter_class')

            if not adapter_module or not adapter_class:
                return {
                    'status': 'error',
                    'test_result': 'failed',
                    'available': False,
                    'message': f'{provider_id} 适配器未实现',
                    'error_code': 'ADAPTER_NOT_IMPLEMENTED'
                }

            try:
                # 动态导入类
                module = __import__(adapter_module, fromlist=[adapter_class])
                provider_class = getattr(module, adapter_class)

                # 创建临时实例（各Provider从配置读取proxy，无需传参）
                test_instance = provider_class()

                # 如果Provider实现了initialize方法，调用它来初始化客户端
                if hasattr(test_instance, 'initialize'):
                    if credential:
                        test_instance.initialize(credential=credential)
                    else:
                        test_instance.initialize()

                # 使用适配器自定义的测试符号
                if hasattr(test_instance, 'get_test_symbol'):
                    test_symbol = test_instance.get_test_symbol()
                else:
                    test_symbol = '^GSPC.US'

                # 🔧 统一使用 pd.Timestamp 类型
                current_time = MarketTimeUtils.get_market_time_now(test_symbol)
                start_date = current_time - pd.Timedelta(days=30)
                end_date = current_time
                start_time = time.time()

                # 执行测试查询
                test_data = test_instance.get_index_prices(test_symbol, start_date, end_date, current_time)

                latency_ms = int((time.time() - start_time) * 1000)

                # 处理PriceData对象
                if hasattr(test_data, 'to_dataframe'):
                    test_data_df = test_data.to_dataframe()
                    is_empty = test_data_df.empty
                    data_count = len(test_data_df)
                else:
                    is_empty = test_data.empty if test_data is not None else True
                    data_count = len(test_data) if test_data is not None else 0

                if test_data is None or is_empty:
                    # 测试失败：连接成功但返回空数据
                    is_available = False
                    message = f'{provider_id} 连接成功，但返回空数据'
                    logger.warning(f"{provider_id} 测试警告: {message}")

                    result = {
                        'status': 'error',
                        'test_result': 'failed',
                        'available': is_available,
                        'message': message,
                        'details': {
                            'test_symbol': test_symbol,
                            'date_range': f'{start_date} to {end_date}',
                            'latency_ms': latency_ms
                        }
                    }
                else:
                    # 测试成功
                    is_available = True
                    message = f'{provider_id} 连接测试通过'
                    logger.info(f"{provider_id} 测试成功: {data_count} 条数据, {latency_ms}ms")

                    result = {
                        'status': 'success',
                        'test_result': 'passed',
                        'available': is_available,
                        'message': message,
                        'details': {
                            'test_symbol': test_symbol,
                            'data_count': data_count,
                            'date_range': f'{start_date} to {end_date}',
                            'latency_ms': latency_ms
                        },
                        'timestamp': pd.Timestamp.now().isoformat()
                    }

                    # 测试成功后，保存凭证到文件
                    if credential:
                        cls.save_credentials(provider_id, credential)
                        logger.info(f"{provider_id} 凭证已保存")

                    # 💚 保存测试状态到配置文件（关键修复）
                    cls.save_test_status(provider_id, 'passed')
                    logger.info(f"{provider_id} 测试状态已保存: passed")

                return result

            except Exception as test_error:
                logger.error(f"测试 {provider_id} 连接失败: {test_error}")
                return {
                    'status': 'error',
                    'test_result': 'failed',
                    'available': False,
                    'message': f'{provider_id} 连接测试失败: {str(test_error)}',
                    'error_code': 'CONNECTION_TEST_FAILED'
                }

        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return {
                'status': 'error',
                'test_result': 'failed',
                'available': False,
                'message': str(e),
                'error_code': 'TEST_CONNECTION_FAILED'
            }

    @classmethod
    def save_credentials(
            cls,
            provider_id: str,
            credential: str,
    ) -> bool:
        """
        保存数据源凭证
        
        Args:
            provider_id: 数据源ID
            credential: 凭证数据
            
        Returns:
            bool: 是否成功
            
        Note:
            凭证保存后不再重置测试状态，状态由下次系统启动时的实时测试决定
        """
        try:
            credentials_yml_path = cls._get_config_path('credentials.yml')

            # 读取现有凭证
            if credentials_yml_path.exists():
                with open(credentials_yml_path, 'r', encoding='utf-8') as f:
                    credentials_data = yaml.safe_load(f) or {}
            else:
                credentials_data = {}

            # 更新凭证
            credentials_data[provider_id] = credential

            # 写入凭证文件
            credentials_yml_path.parent.mkdir(parents=True, exist_ok=True)
            with open(credentials_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(credentials_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            logger.info(f"保存 {provider_id} 凭证成功: {credential}")
            return True

        except Exception as e:
            logger.error(f"保存凭证失败: {e}")
            return False

    @classmethod
    def delete_credentials(
            cls,
            provider_id: str,
    ) -> bool:
        """
        删除数据源凭证
        
        Args:
            provider_id: 数据源ID
            
        Returns:
            bool: 是否成功
        
        Examples:
            >>> BaseDataProvider.delete_credentials('yahoo')
            True
            >>> BaseDataProvider.delete_credentials('nonexistent_provider')
            True  # 即使凭证不存在也返回 True
        
        Note:
            - 如果凭证文件不存在，返回 True（视为已删除）
            - 如果 provider_id 不存在，也返回 True（视为已删除）
            - 只有当文件操作失败时才返回 False
        """
        try:
            credentials_yml_path = cls._get_config_path('credentials.yml')

            # 如果凭证文件不存在，视为已删除
            if not credentials_yml_path.exists():
                logger.info(f"凭证文件不存在，视为已删除: {credentials_yml_path}")
                return True

            # 读取现有凭证
            with open(credentials_yml_path, 'r', encoding='utf-8') as f:
                credentials_data = yaml.safe_load(f) or {}

            # 如果 provider_id 不存在，视为已删除
            if provider_id not in credentials_data:
                logger.info(f"{provider_id} 凭证不存在，视为已删除")
                return True

            # 删除凭证
            del credentials_data[provider_id]

            # 写入文件
            with open(credentials_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(credentials_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            logger.info(f"删除 {provider_id} 凭证成功")
            return True

        except Exception as e:
            logger.error(f"删除凭证失败: {e}")
            return False

    @classmethod
    def save_test_status(
            cls,
            provider_id: str,
            status: str,
    ) -> bool:
        """
        保存数据源测试状态到配置文件
        
        Args:
            provider_id: 数据源ID
            status: 测试状态 ('passed' | 'failed' | 'untested')
            
        Returns:
            bool: 是否成功
            
        Examples:
            >>> BaseDataProvider.save_test_status('yahoo', 'passed')
            True
            >>> BaseDataProvider.save_test_status('akshare', 'failed')
            True
        
        Note:
            - 状态保存到 data_provider.yml 中对应 provider 的 status 字段
            - 直接写入文件,确保持久化
        """
        try:

            from core.share.config_manager import ConfigManager
            import yaml
            import os

            config_manager = ConfigManager()

            # 获取 data_provider.yml 的路径
            data_yml_path = config_manager.get_config_path('data')

            # 读取现有配置
            if os.path.exists(data_yml_path):
                with open(data_yml_path, 'r', encoding='utf-8') as f:
                    data_config = yaml.safe_load(f) or {}
            else:
                logger.error(f"配置文件不存在: {data_yml_path}")
                return False

            # 查找并更新 provider 状态
            providers = data_config.get('providers', [])
            provider_found = False

            for provider in providers:
                if provider.get('id') == provider_id:
                    provider['status'] = status
                    provider['last_test'] = pd.Timestamp.now().isoformat()
                    provider_found = True
                    logger.info(f"更新 provider 状态: {provider_id} -> {status}")
                    break

            if not provider_found:
                logger.warning(f"Provider {provider_id} 不存在于配置文件中")
                return False

            # 💚 关键修复: 写入文件,确保持久化
            with open(data_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(data_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            logger.info(f"{provider_id} 测试状态已保存: {status}")

            # 重新加载配置(更新内存)
            config_manager._load_config()

            return True

        except Exception as e:
            logger.error(f"保存测试状态失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def initialize(self, **kwargs):
        """
        初始化方法（可选实现）

        子类可以重写此方法来进行额外的初始化工作，
        例如根据传入的参数初始化客户端连接等。

        Args:
            **kwargs: 初始化参数
        """
        pass

    def get_all_symbols(self, market: MarketCode) -> pd.DataFrame:
        """
        获取指定市场的所有股票代码列表（基础实现，子类应覆盖）
        
        Args:
            market: 市场枚举
            
        Returns:
            pd.DataFrame: 空DataFrame，子类应实现具体逻辑
        """
        logger.warning(f"BaseDataProvider.get_all_symbols() 未实现具体逻辑，市场: {market}")
        return pd.DataFrame(columns=['symbol', 'name', 'markets'])
    
    def get_complete_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取指定股票的完整基本面数据（基础实现，子类应覆盖）
        
        Args:
            symbol: 股票代码
            
        Returns:
            Dict[str, Any]: 空字典，子类应实现具体逻辑
        """
        logger.warning(f"BaseDataProvider.get_complete_fundamental_data() 未实现具体逻辑，股票: {symbol}")
        return {}

    # ========================================================================
    # 内部接口（子类必须实现）
    # ========================================================================

    def _fetch_today_k_column_from_external_api(self, market_local_time, symbol) -> pd.DataFrame:
        """
        获取当前交易日的K线数据（1分钟级别）

        Args:
            market_local_time: 目标市场当前本地时间（不带时区信息）
            symbol: 股票代码（支持市场后缀，如 '000001.SZ'）

        Returns:
            DataFrame: 包含当前交易日的当天K线数据，列包括：
                - date: pd.Timestamp 类型，交易日期时间
                - open: float，开盘价
                - high: float，最高价
                - low: float，最低价
                - close: float，收盘价
                - volume: float，成交量
        """
        pass

    def _fetch_real_intraday_from_external_api(self, symbol: str, start_time_str: str,
                                               end_time_str: str) -> pd.DataFrame:
        """
        从数据源获取分时数据（子类必须实现）

        Args:
            symbol: 证券代码
            start_time_str: 开始时间
            end_time_str: 结束时间

        Returns:
            pd.DataFrame: 分时数据 DataFrame
        """
        pass

    @abstractmethod
    def _fetch_history_kline_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp,
                                               period: str = 'daily'):
        """
        从外部API获取数据（抽象方法，子类必须实现）

        Args:
            symbol: 股票/指数代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: 数据粒度 ('daily'/'weekly'/'monthly'，告诉API返回什么粒度，默认 daily)

        Returns:
            PriceData: 价格数据对象

        Raises:
            Exception: API调用失败时抛出异常
        """
        pass

    def _to_IntradayData(self, df: pd.DataFrame, symbol: str, trade_date: pd.Timestamp,
                         interpolate_func=None) -> IntradayData:
        """
        将DataFrame转换为IntradayData对象

        Args:
            df: DataFrame，包含分时数据
            symbol: 证券代码
            trade_date: 交易日期
            interpolate_func: 插值函数，用于处理缺失数据

        Returns:
            IntradayData: 完整分时数据对象
        """

    def _fetch_realtime_order_book_from_external_api(self, symbol: str) -> Optional[tuple[list, list]]:
        """
        获取实时盘口数据（买卖五档）

        Args:
            symbol: 证券代码（带后缀，如000300.SH）

        Returns:
            (order_book_bids, order_book_asks): 买盘列表, 卖盘列表

        注意：
        - 只在交易时间内调用此方法
        - 非交易时间返回空列表
        """
        pass

    def _fetch_realtime_trade_records_from_external_api(self, symbol):
        """
        从数据源获取实时成交记录

        Args:
            symbol: 标的代码

        Returns:
            list: 成交记录列表
        """
        pass
