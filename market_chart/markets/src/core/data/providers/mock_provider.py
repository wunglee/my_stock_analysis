"""
模拟数据提供者（与真实数据规则一致）

职责：
1. 生成模拟的分时数据（fallback方案）
2. 提供实时K线数据计算

用途：当真实数据源不可用时，提供模拟数据用于开发和测试

设计原则（与 AKShareDataProvider 保持一致）：
1. 盘前时段（before_open）：返回空数据，但个股有盘口
2. 交易时段（trading）：返回实时数据 + 盘口 + 成交明细
3. 午休时段（noon_break）：返回上午数据 + 盘口
4. 盘后时段（after_close）：返回全天数据，无盘口
5. 指数：任何时段都没有盘口和成交明细

技术特性：
- 使用 TickRange 替代 batches 参数
- 基于时间范围生成连续的05秒粒度tick数据
- 支持价格连续性（通过 last_price 参数）
- 模拟真实市场的价格波动特性（趋势 + 随机波动 + 突发波动 + 均值回归）
- 提供实时K线数据计算（带缓存优化）
"""

import logging
import random
from typing import Optional, Tuple, List

import pandas as pd

from core.data.providers.base_provider import BaseDataProvider
from core.data.providers.protocols import (
    IntradayData, IntradayTickRecord, OrderBookLevel, TradeDetailRecord, TickRange
)
from core.share.market.market_enums import TradingPhase

logger = logging.getLogger(__name__)


class MockDataProvider(BaseDataProvider):
    """模拟数据提供者（分时数据 + 实时K线 + 历史K线）"""

    # 股票名称映射
    NAME_MAP = {
        '000001.SH': '上证指数',
        '000300.SH': '沪深300',
        '399001.SZ': '深证成指',
        '399006.SZ': '创业板指',
        '^GSPC': 'S&P 500',
        'AAPL': 'Apple Inc.'
    }
    
    # 🔧 Mock模式的实时K线缓存（内存缓存，独立于真实数据）
    # key格式: "mock_realtime_{symbol}_{date}_{trading_phase}"
    _mock_realtime_cache = {}

    def __init__(self):
        """初始化生成器"""
        super().__init__()
        # 🔧 Mock数据禁用所有缓存，避免污染真实数据缓存
        self._enable_memory_cache = False
        self._enable_db_cache = False
        # 🎭 Mock模式存储前端传入的trading_phase（用于needs_realtime_kline判断）
        self._mock_trading_phase = None
    
    def set_mock_trading_phase(self, trading_phase: TradingPhase):
        """设置Mock模式的交易时段（由前端控制）"""
        self._mock_trading_phase = trading_phase
        logger.info(f"🎭 设置Mock交易时段: {trading_phase.name}")
    
    def set_needs_realtime_kline(self, price_data, current_time: pd.Timestamp):
        """
        🎭 Mock模式：根据前端传入的trading_phase设置needs_realtime_kline
        
        覆写基类方法，不使用current_time判断，而是使用前端传入的trading_phase
        
        Args:
            price_data: 价格数据对象
            current_time: 当前时间（Mock模式忽略此参数）
        """
        # 🎭 关键：使用前端传入的trading_phase，不使用current_time判断
        if self._mock_trading_phase:
            price_data.needs_realtime_kline = self._mock_trading_phase in [
                TradingPhase.BEFORE_OPEN,
                TradingPhase.TRADING,
                TradingPhase.NOON_BREAK
            ]
            logger.info(f"🎭 Mock模式 - trading_phase={self._mock_trading_phase.name}, needs_realtime_kline={price_data.needs_realtime_kline}")
        else:
            # 如果没有设置Mock时段，默认不需要实时K线
            price_data.needs_realtime_kline = False
            logger.warning("🎭 Mock模式未设置trading_phase，默认needs_realtime_kline=False")

    def _fetch_history_kline_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str = 'daily'):
        """
        生成模拟历史K线数据

        注意：历史K线都是已完成的交易日数据，不涉及交易时段判断
        
        🔧 Mock数据不使用缓存，每次都重新生成（避免真实数据和模拟数据混淆）
        
        🎭 Mock模式规则：
        - 盘后（after_close）：历史数据生成到今天（今天的K线已完成）
        - 盘前/盘中（before_open/trading）：历史数据只生成到昨天（今天的K线由实时接口提供）

        Args:
            symbol: 证券代码
            start_date: 开始日期 (pd.Timestamp)
            end_date: 结束日期 (pd.Timestamp)
            period: 周期 ('daily', 'weekly', 'monthly') - Mock数据忽略此参数，总是生成日线

        Returns:
            PriceData: 包含OHLCV数据的结构化对象
        """
        import pandas as pd
        from core.data.providers.protocols import PriceData

        logger.info(f"📊 生成模拟K线: {symbol}, {start_date} ~ {end_date}")

        # 🔧 确保输入是 pd.Timestamp 类型
        if not isinstance(start_date, pd.Timestamp):
            start_date = pd.to_datetime(start_date)
        if not isinstance(end_date, pd.Timestamp):
            end_date = pd.to_datetime(end_date)
        
        # 转换日期
        start_dt = start_date
        end_dt = end_date
        
        # 🎭 关键：根据_mock_trading_phase决定是否包含今天
        today = pd.Timestamp.now().date()
        if end_dt.date() == today and end_dt.weekday() < 5:  # 周一到周五
            # 如果是盘前或盘中，历史数据只到昨天
            if self._mock_trading_phase in [TradingPhase.BEFORE_OPEN, TradingPhase.TRADING, TradingPhase.NOON_BREAK]:
                end_dt = end_dt - pd.Timedelta(days=1)
                logger.info(f"🎭 盘前/盘中时段，历史K线只到昨天: {end_dt.strftime('%Y-%m-%d')}")
            elif self._mock_trading_phase == TradingPhase.AFTER_CLOSE:
                logger.info(f"🎭 盘后时段，历史K线包含今天: {end_dt.strftime('%Y-%m-%d')}")
            else:
                # 如果没有设置_mock_trading_phase，默认不包含今天
                end_dt = end_dt - pd.Timedelta(days=1)
                logger.warning(f"🎭 未设置trading_phase，默认历史K线只到昨天: {end_dt.strftime('%Y-%m-%d')}")

        # 生成交易日期序列（跳过周末）
        dates = []
        current_dt = start_dt
        while current_dt <= end_dt:
            # 跳过周末（0=周一, 6=周日）
            if current_dt.weekday() < 5:
                dates.append(current_dt)
            current_dt += pd.Timedelta(days=1)

        # 生成基准价格（使用固定种子保证一致性）
        random.seed(symbol)
        base_price = 3000 + random.random() * 300

        # 生成OHLCV数据
        data_rows = []
        current_price = base_price

        for i, date in enumerate(dates):
            date_str = date.strftime('%Y-%m-%d')

            # 使用日期作为种子，保证每天的数据可重复
            random.seed(symbol + date_str)

            # 生成当天的OHLCV
            daily_change = (random.random() - 0.5) * current_price * 0.03  # ±3%波动
            open_price = current_price + (random.random() - 0.5) * current_price * 0.01
            close_price = current_price + daily_change
            high_price = max(open_price, close_price) + random.random() * current_price * 0.01
            low_price = min(open_price, close_price) - random.random() * current_price * 0.01
            volume = int(1000000 + random.random() * 500000)

            data_rows.append({
                'date': date_str,
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': volume
            })

            # 更新下一天的基准价格
            current_price = close_price

        # 转换为DataFrame
        df = pd.DataFrame(data_rows)

        logger.info(f"✅ 生成完成: {len(df)}条K线数据")

        price_data = PriceData.from_dataframe(df, symbol)
        return price_data
    
    def get_intraday_data(self, symbol: str, tick_range: Optional[TickRange] = None,
                          market_local_time: pd.Timestamp = None) -> IntradayData:
        """
        伪实现：仅用于满足 HistoricalDataProvider 抽象接口要求
        
        注意：
        - MockDataProvider 的实际使用中，API 直接调用 generate() 方法
        - 此方法不应被调用，只是为了确保 MockDataProvider 可以被实例化
        - 如果意外被调用，会抛出 NotImplementedError
        
        Args:
            symbol: 证券代码
            tick_range: Tick数据时间范围
            market_local_time: 当前时间
        
        Raises:
            NotImplementedError: 总是抛出，因为实际应该调用 generate() 方法
        """
        raise NotImplementedError(
            f"MockDataProvider.get_intraday_data() 是伪实现，不应被调用。\n"
            f"\n"
            f"请直接调用 generate_intraday_data() 方法：\n"
            f"  mock_provider.generate_intraday_data(\n"
            f"      symbol='{symbol}',\n"
            f"      trade_date=pd.Timestamp.now(),\n"
            f"      tick_range=tick_range,\n"
            f"      trading_phase=TradingPhase.TRADING,\n"
            f"      is_index=False\n"
            f"  )\n"
            f"\n"
            f"参考: api_service_mock.py 第293行和第640行"
        )

    def generate_intraday_data(self, symbol: str, trade_date: pd.Timestamp, tick_range: Optional[TickRange] = None,
                               trading_phase: TradingPhase = TradingPhase.TRADING, last_price: Optional[float] = None,
                               is_index: bool = False) -> IntradayData:
        """
        生成模拟分时数据（与真实数据规则一致）
        
        规则（与 AKShareDataProvider.get_intraday_data 一致）：
        1. 盘前时段（before_open）：返回空数据，但个股有盘口
        2. 交易时段（trading）：返回实时数据 + 盘口 + 成交明细
        3. 午休时段（noon_break）：返回上午数据 + 盘口
        4. 盘后时段（after_close）：返回全天数据，无盘口
        5. 指数：任何时段都没有盘口和成交明细
        
        Args:
            symbol: 证券代码
            trade_date: 交易日期 (pd.Timestamp)
            tick_range: Tick数据时间范围，如果None则根据交易时段自动计算
            trading_phase: 交易时段（TradingPhase枚举）
            last_price: 上次请求的最终价格，用于保证价格连续性
            is_index: 是否为指数
        
        Returns:
            IntradayData: 分时数据对象
        """
        # 🔧 类型安全：如果 trade_date 是 pd.Timestamp，转换为字符串
        if isinstance(trade_date, pd.Timestamp):
            trade_date_str = trade_date.strftime('%Y-%m-%d')
        else:
            trade_date_str = str(trade_date)
        
        # 确保使用枚举类型
        phase = TradingPhase.parse(trading_phase) if isinstance(trading_phase, str) else trading_phase
        logger.info(f"📊 生成模拟数据 - 交易时段: {phase}, 日期: {trade_date_str}, 是否指数: {is_index}")

        # 获取股票名称
        name = self.NAME_MAP.get(symbol, symbol)

        # 生成基准价格（使用固定种子保证一致性）
        random.seed(symbol + trade_date_str)
        base_price = 3000 + random.random() * 300
        yesterday_close = base_price
        logger.info(f"💰 生成基准价: {base_price:.2f}")

        # 计算起始价格（优先使用 last_price 保证连续性）
        start_price = last_price if last_price is not None else base_price

        # 🔧 根据交易时段生成数据（与真实数据一致）
        ticks = []
        current_price = start_price
        fetch_order_book = False  # 是否获取盘口

        if phase == TradingPhase.BEFORE_OPEN:
            # 🔧 盘前时段：返回空数据，但个股有盘口
            logger.info("🕒 盘前时段，返回空数据（个股有盘口）")
            ticks = []  # 空数据
            fetch_order_book = not is_index  # 个股有盘口，指数没有

        elif phase == TradingPhase.TRADING:
            # 🔧 交易时段：返回实时数据 + 盘口 + 成交明细
            logger.info("📊 交易时段，返回实时数据 + 盘口 + 成交明细")
            # 如果未提供 tick_range，根据交易时段自动创建
            if tick_range is None:
                tick_range = TickRange.from_trading_phase(phase, trade_date_str)
                logger.info(f"📅 自动创建 TickRange: {tick_range.start_time} ~ {tick_range.end_time}")

            # 生成分时数据
            ticks, current_price = self._build_ticks_from_range(
                symbol=symbol,
                tick_range=tick_range,
                start_price=start_price
            )
            fetch_order_book = not is_index  # 个股有盘口，指数没有

        elif phase == TradingPhase.NOON_BREAK:
            # 🔧 午休时段：返回上午数据 + 盘口
            logger.info("🌞 午休时段，返回上午数据 + 盘口")
            # 构建上午时间范围（09:30-11:30）
            morning_tick_range = TickRange(
                start_time=pd.Timestamp(f"{trade_date_str} 09:30:00"),
                end_time=pd.Timestamp(f"{trade_date_str} 11:30:00"),
                period_seconds=5
            )
            # 生成上午的分时数据
            ticks, current_price = self._build_ticks_from_range(
                symbol=symbol,
                tick_range=morning_tick_range,
                start_price=start_price
            )
            fetch_order_book = not is_index  # 个股有盘口，指数没有

        elif phase == TradingPhase.AFTER_CLOSE:
            # 🔧 盘后时段：返回全天数据，无盘口
            logger.info("🌙 盘后时段，返回全天数据（无盘口）")
            # 构建全天时间范围（09:30-15:00）
            full_day_tick_range = TickRange(
                start_time=pd.Timestamp(f"{trade_date_str} 09:30:00"),
                end_time=pd.Timestamp(f"{trade_date_str} 15:00:00"),
                period_seconds=5
            )
            # 生成全天的分时数据
            ticks, current_price = self._build_ticks_from_range(
                symbol=symbol,
                tick_range=full_day_tick_range,
                start_price=start_price
            )
            fetch_order_book = False  # 盘后无盘口

        # 计算涨跌
        change = current_price - yesterday_close
        change_percent = (change / yesterday_close * 100) if yesterday_close > 0 else 0

        # 🔧 计算 should_poll 字段（盘前或盘中需要轮询）
        should_poll = phase in [TradingPhase.BEFORE_OPEN, TradingPhase.TRADING]

        # 🔧 根据规则生成盘口和成交明细
        order_book_bids = []
        order_book_asks = []
        trade_records = []
        order_book_message = ''
        trade_records_message = ''

        if is_index:
            # 指数：任何时段都没有盘口和成交明细
            order_book_message = '指数不可交易'
            trade_records_message = '指数无成交明细'
        else:
            # 个股：根据 fetch_order_book 决定是否生成盘口
            if fetch_order_book:
                order_book_bids, order_book_asks = self._generate_order_book(current_price)
                # 只有交易时段才有成交明细
                if phase == TradingPhase.TRADING and len(ticks) > 0:
                    trade_records = self._generate_trade_details(current_price,
                                                                 ticks[-20:] if len(ticks) >= 20 else ticks)
                elif phase == TradingPhase.NOON_BREAK and len(ticks) > 0:
                    # 午休时段可以显示上午最后的成交明细
                    trade_records = self._generate_trade_details(current_price,
                                                                 ticks[-20:] if len(ticks) >= 20 else ticks)

        logger.info(
            f"✅ 生成完成: {len(ticks)}个tick, {len(order_book_bids)}个买盘, {len(order_book_asks)}个卖盘, {len(trade_records)}条成交")

        return IntradayData(
            symbol=symbol,
            name=name,
            current_price=round(current_price, 2),
            yesterday_close=round(yesterday_close, 2),
            change=round(change, 2),
            change_percent=round(change_percent, 2),
            ticks=ticks,
            order_book_bids=order_book_bids,
            order_book_asks=order_book_asks,
            trade_records=trade_records,
            trade_date=trade_date_str,
            order_book_message=order_book_message,
            trade_records_message=trade_records_message,
            is_index=is_index,
            should_poll=should_poll  # 🔧 设置 should_poll 字段
        )

    def _build_ticks_from_range(self, symbol: str, tick_range: TickRange,
                                start_price: float) -> Tuple[List[IntradayTickRecord], float]:
        """
        根据时间范围构建分时tick数据
        
        Args:
            symbol: 证券代码
            tick_range: 时间范围
            start_price: 起始价格
        
        Returns:
            (ticks, final_price): 分时tick列表和最终价格
        """
        ticks = []
        total_volume = 0
        total_amount = 0
        current_price = start_price

        # 遍历时间范围内的每个tick点
        current_time = tick_range.start_time
        tick_index = 0

        while current_time <= tick_range.end_time:
            # 跳过午休时段 (12:00-13:00)
            if 12 <= current_time.hour < 13:
                current_time += pd.Timedelta(seconds=tick_range.period_seconds)
                continue

            # 使用时间戳作为随机种子，确保每个时间点的波动是固定的（可重复）
            # 但不同时间点之间是随机的
            time_seed = int(current_time.timestamp())
            random.seed(symbol + str(time_seed))

            # 🔧 价格波动：更真实的市场模拟
            # 1. 主趋势：轻微的随机漂移（避免单向趋势）
            trend = (random.random() - 0.5) * 0.3

            # 2. 随机波动：每个tick的随机变化
            random_change = (random.random() - 0.5) * 0.8

            # 3. 突发波动：偶尔的大幅波动
            spike = 0
            if random.random() > 0.92:  # 8%概率
                spike = (random.random() - 0.5) * 1.5

            # 4. 均值回归：价格离起始价太远时，增加回归压力
            price_diff = current_price - start_price
            mean_reversion = -price_diff * 0.01  # 1%的回归力度

            # 综合波动
            price_change = trend + random_change + spike + mean_reversion
            current_price += price_change

            volume = random.randint(500, 2000)

            total_volume += volume
            total_amount += current_price * volume
            avg_price = total_amount / total_volume if total_volume > 0 else current_price

            ticks.append(IntradayTickRecord(
                time=current_time.strftime('%H:%M:%S'),
                price=round(current_price, 2),
                volume=volume,
                avg_price=round(avg_price, 2)
            ))

            current_time += pd.Timedelta(seconds=tick_range.period_seconds)
            tick_index += 1

        return ticks, current_price

    def _generate_order_book(self, current_price: float) -> Tuple[List[OrderBookLevel], List[OrderBookLevel]]:
        """
        生成模拟盘口数据（每次调用都会变化）
        
        Args:
            current_price: 当前价格
        
        Returns:
            (order_book_bids, order_book_asks): 买盘和卖盘列表
        """
        # 🔧 使用当前时间作为种子，让盘口每次都不同
        import time
        random.seed(int(time.time() * 1000))  # 毫秒级别的种子

        order_book_bids = []
        order_book_asks = []

        for i in range(1, 11):
            order_book_bids.append(OrderBookLevel(
                price=round(current_price - i * 0.01, 2),
                volume=random.randint(1000, 10000)
            ))
            order_book_asks.append(OrderBookLevel(
                price=round(current_price + i * 0.01, 2),
                volume=random.randint(1000, 10000)
            ))

        return order_book_bids, order_book_asks

    def _generate_trade_details(self, current_price: float,
                                recent_ticks: List[IntradayTickRecord]) -> List[TradeDetailRecord]:
        """
        生成模拟成交明细（逐笔成交记录，每次调用都会变化）
        
        Args:
            current_price: 当前价格
            recent_ticks: 最近的tick数据，用于生成更真实的成交明细
        
        Returns:
            成交明细列表
        """
        # 🔧 使用当前时间作为种子，让成交明细每次都不同
        import time
        random.seed(int(time.time() * 1000))  # 毫秒级别的种子

        trade_records = []

        # 基于最近的tick数据生成成交明细
        if recent_ticks and len(recent_ticks) > 0:
            for tick in reversed(recent_ticks[-20:]):  # 最多20条
                trade_records.append(TradeDetailRecord(
                    time=tick.time,
                    price=tick.price,
                    volume=random.randint(100, 500),  # 单笔成交量
                    direction=random.choice(['buy', 'sell'])
                ))
        else:
            # 如果没有tick数据，生成随机的成交明细
            now = pd.Timestamp.now()
            for i in range(20):
                tick_time = now - pd.Timedelta(seconds=i * 5)
                trade_records.append(TradeDetailRecord(
                    time=tick_time.strftime('%H:%M:%S'),
                    price=round(current_price + (random.random() - 0.5) * 0.2, 2),
                    volume=random.randint(100, 2000),
                    direction=random.choice(['buy', 'sell'])
                ))

        return trade_records

    def get_realtime_kline(self, symbol: str, trade_date: pd.Timestamp, trading_phase: TradingPhase,
                           is_index: bool, cached: Optional[dict] = None) -> dict:
        """
        获取实时K线数据（领域层方法）
        
        注意：MockProvider用于前端开发测试，需要前端显式传入trading_phase进行模拟控制
        
        职责：
        1. 根据交易时段生成模拟数据
        2. 使用独立内存缓存维护开盘价和极值（避免污染真实缓存）
        3. 盘前时段：只返回开盘价（high/low/close都等于open）
        4. 盘中时段：返回完整OHLCV，在缓存基础上维护极值
        5. 盘后时段：返回完整K线数据
        
        Args:
            symbol: 证券代码
            trade_date: 交易日期 (pd.Timestamp)
            trading_phase: 交易时段（由前端控制，用于模拟）
            is_index: 是否为指数
            cached: （已废弃，保留用于兼容）
        
        Returns:
            {
                'date': str,
                'open': float,       # 盘前/盘中/盘后都有
                'high': float | None,  # 盘前为None，盘中/盘后有值
                'low': float | None,   # 盘前为None，盘中/盘后有值
                'close': float,      # 盘前/盘中/盘后都有
                'volume': int,
                'trading_phase': str,
                'should_poll': bool
            }
        """
        import time
        
        # 🔧 转换为字符串
        if isinstance(trade_date, pd.Timestamp):
            trade_date_str = trade_date.strftime('%Y-%m-%d')
        else:
            trade_date_str = str(trade_date)

        # 🔧 构建Mock专用缓存key（避免与真实缓存冲突）
        cache_key = f"mock_realtime_{symbol}_{trade_date_str}_{trading_phase.name}"
        
        # 🔧 是否应该启动轮询（盘前或盘中）
        should_poll = trading_phase in [TradingPhase.BEFORE_OPEN, TradingPhase.TRADING]
        
        # 生成基准价格
        random.seed(symbol + trade_date_str)
        base_price = 3000 + random.random() * 300
        
        # 🔧 盘前时段：只返回开盘价（模拟集合竞价）
        if trading_phase == TradingPhase.BEFORE_OPEN:
            # 检查缓存，如果没有则初始化
            if cache_key not in self._mock_realtime_cache:
                # 初始化：生成开盘价（在基准价±1%范围内波动）
                random.seed(symbol + trade_date_str + str(int(time.time() * 1000)))
                open_price = base_price * (1 + (random.random() - 0.5) * 0.02)
                
                self._mock_realtime_cache[cache_key] = {
                    'open': open_price,
                    'high': open_price,  # 盘前 high=open
                    'low': open_price,   # 盘前 low=open
                    'volume': 0
                }
                logger.info(f"🎭 盘前初始化缓存: open={open_price:.2f}")
            
            cached_data = self._mock_realtime_cache[cache_key]
            
            return {
                'date': trade_date_str,
                'open': round(cached_data['open'], 2),
                'high': round(cached_data['high'], 2),  # 盘前 high=open
                'low': round(cached_data['low'], 2),    # 盘前 low=open
                'close': round(cached_data['open'], 2),  # 盘前收盘价=开盘价
                'volume': 0,
                'trading_phase': trading_phase.name,
                'should_poll': should_poll
            }
        
        # 🔧 盘中时段：返回完整OHLCV，维护极值
        elif trading_phase == TradingPhase.TRADING:
            # 使用当前时间戳作为随机种子，让每次调用都生成不同的数据
            current_timestamp = int(time.time() * 1000)
            random.seed(symbol + trade_date_str + str(current_timestamp))
            
            # 检查缓存，如果没有则从盘前缓存继承，或者初始化
            if cache_key not in self._mock_realtime_cache:
                # 尝试从盘前缓存继承开盘价
                before_cache_key = f"mock_realtime_{symbol}_{trade_date_str}_BEFORE_OPEN"
                if before_cache_key in self._mock_realtime_cache:
                    open_price = self._mock_realtime_cache[before_cache_key]['open']
                    logger.info(f"🎭 从盘前继承开盘价: {open_price:.2f}")
                else:
                    # 如果没有盘前数据，初始化开盘价
                    open_price = base_price * (1 + (random.random() - 0.5) * 0.01)
                    logger.info(f"🎭 盘中初始化开盘价: {open_price:.2f}")
                
                # 初始化缓存
                current_price = open_price + (random.random() - 0.5) * open_price * 0.01
                self._mock_realtime_cache[cache_key] = {
                    'open': open_price,
                    'high': max(open_price, current_price),
                    'low': min(open_price, current_price),
                    'volume': random.randint(100000, 200000)
                }
            
            # 获取缓存数据
            cached_data = self._mock_realtime_cache[cache_key]
            
            # 生成当前价格（在开盘价±2%范围内波动）
            current_price = cached_data['open'] + (random.random() - 0.5) * cached_data['open'] * 0.04
            
            # 维护极值
            cached_data['high'] = max(cached_data['high'], current_price)
            cached_data['low'] = min(cached_data['low'], current_price)
            cached_data['volume'] += random.randint(10000, 50000)  # 累加成交量
            
            logger.info(
                f"📊 盘中实时K线: open={cached_data['open']:.2f}, close={current_price:.2f}, "
                f"high={cached_data['high']:.2f}, low={cached_data['low']:.2f}, volume={cached_data['volume']}")
            
            return {
                'date': trade_date_str,
                'open': round(cached_data['open'], 2),
                'high': round(cached_data['high'], 2),
                'low': round(cached_data['low'], 2),
                'close': round(current_price, 2),
                'volume': cached_data['volume'],
                'trading_phase': trading_phase.name,
                'should_poll': should_poll
            }
        
        # 🔧 盘后时段：返回完整的当天K线数据（不再变化）
        else:
            # 尝试从盘中缓存获取数据
            trading_cache_key = f"mock_realtime_{symbol}_{trade_date_str}_TRADING"
            if trading_cache_key in self._mock_realtime_cache:
                cached_data = self._mock_realtime_cache[trading_cache_key]
                logger.info(f"🌙 盘后使用盘中数据: {cached_data}")
                
                return {
                    'date': trade_date_str,
                    'open': round(cached_data['open'], 2),
                    'high': round(cached_data['high'], 2),
                    'low': round(cached_data['low'], 2),
                    'close': round(cached_data['open'] + (random.random() - 0.5) * cached_data['open'] * 0.02, 2),
                    'volume': cached_data['volume'],
                    'trading_phase': trading_phase.name,
                    'should_poll': False
                }
            else:
                # 如果没有盘中数据，生成固定的K线数据
                open_price = base_price * (1 + (random.random() - 0.5) * 0.01)
                close_price = open_price + (random.random() - 0.5) * open_price * 0.02
                high_price = max(open_price, close_price) + random.random() * open_price * 0.01
                low_price = min(open_price, close_price) - random.random() * open_price * 0.01
                volume = random.randint(500000, 1000000)
                
                logger.info(f"🌙 盘后生成完整K线数据")
                
                return {
                    'date': trade_date_str,
                    'open': round(open_price, 2),
                    'high': round(high_price, 2),
                    'low': round(low_price, 2),
                    'close': round(close_price, 2),
                    'volume': volume,
                    'trading_phase': trading_phase.name,
                    'should_poll': False
                }
