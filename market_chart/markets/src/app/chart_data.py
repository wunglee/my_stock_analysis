"""图表数据组装模块

[应用层 - API组件] 图表数据导出功能
状态: ✅ 新增 - 合并数据流API
创建时间: 2025-12-06

职责：
- 组装K线+技术指标+事件的完整图表数据
- 作为应用层胶水层，连接领域层指标服务和数据提供者
- 仅包含数据格式转换和组装逻辑，不包含业务计算

架构原则：
- 依赖领域层的 IndicatorService（技术指标计算）
- 依赖数据提供者接口（数据获取）
- 符合单一职责原则（SRP）：只负责数据组装
- 符合开闭原则（OCP）：扩展新指标无需修改现有代码
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from core.data.providers.protocols import PriceData, TickRange
from core.share.market.market_time_utils import MarketTimeUtils

logger = logging.getLogger('App.API.ChartData')


class ChartDataAssembler:
    """图表数据组装器
    
    职责：
    1. 获取K线数据（使用领域层标准 PriceData 类型）
    2. 调用领域层服务计算技术指标
    3. 检测市场事件
    4. 组装完整的图表数据结构
    
    依赖倒置原则（DIP）：
    - 依赖抽象的数据提供者接口，不依赖具体实现
    - 依赖抽象的指标服务接口，不依赖具体实现
    - 使用领域层标准类型 PriceData，避免非强类型 DataFrame
    """
    
    def __init__(self, data_provider: Any, indicator_service: Any) -> None:
        """初始化图表数据组装器
        
        Args:
            data_provider: 数据提供者（实现 get_index_prices 接口）
            indicator_service: 技术指标服务（IndicatorService 实例）
        
        💚 注意: DataProvider 已内置三层缓存，此处不需再处理
        """
        self._data_provider = data_provider
        self._indicator_service = indicator_service
    
    def assemble_chart_data(self,
                           symbol: str,
                           period: str = 'daily',
                           count: int = 120,
                           before: Optional[pd.Timestamp] = None,
                           indicators: Optional[str] = 'all',
                           market_local_time:pd.Timestamp=None) -> Dict[str, Any]:
        """组装完整的图表数据（全程使用强类型 PriceData）
        
        🆕 新逻辑：在交易时段（盘前/盘中），将历史数据和实时数据分离：
        - 非交易时段：返回完整的历史数据（包含最后一个周期）
        - 交易时段：除最后一个周期（留给实时数据叠加）
        
        Args:
            symbol: 股票/指数代码
            period: 周期（daily/weekly/monthly）
            count: 数据条数
            before: 获取此日期之前的数据（pd.Timestamp 类型）
            indicators: 需要的指标（逗号分隔或 'all'）
            market_local_time: 当前市场本地时间（默认自动获取）
        
        Returns:
            {
                'kline': [...],  # K线数据（包含MA）
                'indicators': {...},  # 技术指标数据
                'events': [...],  # 事件数据
                'needs_realtime_kline': bool  # 🔧 是否需要获取实时K线（盘前/盘中/午盘为True，盘后为False）
            }
        
        Raises:
            ValueError: 参数无效
            RuntimeError: 数据获取或计算失败
        """
        try:
            # 🔧 如果没有传入market_local_time，自动获取市场本地时间
            if market_local_time is None:
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)
            
            # 确保 market_local_time 带有正确的市场时区
            market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, symbol)
            
            logger.info(f"开始组装图表数据: symbol={symbol}, period={period}, count={count}, before={before}")
            
            # 1. 获取K线数据（🔧 额外获取预热数据用于指标计算，返回 PriceData）
            logger.info("步骤1: 获取K线数据...")
            # 🔧 根据周期类型调整预热数量：月线3条、周线10条、日线30条
            if period == 'monthly':
                warmup_count = 3  # 月线：3个月预热（MACD需要26个周期，但月线数据量少）
            elif period == 'weekly':
                warmup_count = 10  # 周线：10周预热（约2.5个月）
            else:
                warmup_count = 30  # 日线：30天预热（约1个月）
            price_data_full = self._fetch_kline_data(symbol, period, count + warmup_count, before, market_local_time)
            
            # 🔧 关键修复：数据为空时直接返回空结果（无限滚动到头）
            if price_data_full is None or price_data_full.count == 0:
                logger.info(f"⚠️ 无数据：{symbol}，返回空结果（可能是无限滚动到头）")
                return {
                    'kline': [],
                    'indicators': {},
                    'events': [],
                    'needs_realtime_kline': False
                }
            
            logger.info(f"K线数据获取成功，共 {price_data_full.count} 条（包含{warmup_count}条预热数据）")
            
            # 🆕 新逻辑：在交易时段，需要排除最后一个周期K柱（留给实时数据）
            exclude_last_bar = price_data_full.needs_realtime_kline
            last_bar_for_cache = None  # 用于缓存的最后一个K柱
            
            if exclude_last_bar:
                logger.info(f"🔄 交易时段，排除最后一个{period}周期K柱，留给实时数据叠加")
                # 从完整数据中移除最后一条
                price_data_for_calculation = self._slice_price_data(price_data_full, 0, -1)
                
                # 💾 缓存最后一个K柱（用于实时K线合并）
                if period in ['weekly', 'monthly'] and price_data_full.count > 0:
                    last_record = price_data_full.records[-1]
                    last_bar_for_cache = {
                        'date': last_record.date.strftime('%Y-%m-%d'),
                        'open': float(last_record.open),
                        'high': float(last_record.high),
                        'low': float(last_record.low),
                        'close': float(last_record.close),
                        'volume': int(last_record.volume)
                    }
                    # 构建缓存key
                    cache_key = f"last_period_bar_{symbol}_{period}"
                    # 存入内存缓存（使用DataProvider的缓存机制）
                    self._data_provider._set_to_memory_cache_obj(cache_key, last_bar_for_cache)
                    logger.info(f"💾 缓存最后一个{period}K柱: date={last_bar_for_cache['date']}, open={last_bar_for_cache['open']:.2f}")
            else:
                price_data_for_calculation = price_data_full
            
            # 2. 计算技术指标（使用完整 PriceData）
            logger.info(f"步骤2: 计算技术指标 ({indicators})...")
            kline_with_ma_full, indicators_data_full = self._calculate_indicators(price_data_for_calculation, indicators)
            logger.info(f"技术指标计算成功: {list(indicators_data_full.keys())}")
            
            # 🔧 关键优化：裁剪掉预热数据，只返回请求的条数
            kline_with_ma = kline_with_ma_full[-count:] if len(kline_with_ma_full) > count else kline_with_ma_full
            indicators_data = {
                key: value[-count:] if len(value) > count else value
                for key, value in indicators_data_full.items()
            }
            
            # 🔧 添加详细日志，诊断数据不一致问题
            logger.info(f"裁剪后的数据: kline={len(kline_with_ma)} 条, exclude_last_bar={exclude_last_bar}")
            for key, value in indicators_data.items():
                logger.info(f"  - {key}: {len(value)} 条")
            
            # 🔧 验证数据一致性
            vol_count = len(indicators_data.get('vol', []))
            if vol_count != len(kline_with_ma):
                logger.error(f"⚠️ 数据不一致！kline={len(kline_with_ma)}, vol={vol_count}")
                logger.error(f"  - kline_with_ma_full 长度: {len(kline_with_ma_full)}")
                logger.error(f"  - indicators_data_full['vol'] 长度: {len(indicators_data_full.get('vol', []))}")
                logger.error(f"  - 请求的 count: {count}")
            
            # 3. 检测市场事件（只在请求的范围内，使用裁剪后的 PriceData）
            logger.info("步骤3: 检测市场事件...")
            price_data_requested = self._slice_price_data(price_data_for_calculation, -count, None)
            # 💚 强类型: 直接传入 PriceData 对象
            events = self._detect_events(price_data_requested)
            logger.info(f"事件检测成功，共 {len(events)} 个事件")
            
            # 4. 计算筹码分布
            logger.info("步骤4: 计算筹码分布...")
            chip_distribution = self._calculate_chip_distribution(price_data_requested)
            logger.info(f"筹码分布计算完成，共 {len(chip_distribution)} 个日期")

            # 5. 组装返回数据（包含 needs_realtime_kline 标记）
            result = {
                'kline': kline_with_ma,
                'indicators': indicators_data,
                'events': events,
                'chipDistribution': chip_distribution,
                'needs_realtime_kline': price_data_full.needs_realtime_kline  # 🔧 从 PriceData 中获取标记
            }
            logger.info(f"图表数据组装完成: kline={len(kline_with_ma)} 条, indicators={len(indicators_data)} 个, events={len(events)} 个, needs_realtime_kline={price_data_full.needs_realtime_kline}")
            return result
        
        except Exception as e:
            logger.error(f"组装图表数据失败: {e}", exc_info=True)
            logger.error(f"  - symbol: {symbol}")
            logger.error(f"  - period: {period}")
            logger.error(f"  - count: {count}")
            logger.error(f"  - before: {before}")
            logger.error(f"  - indicators: {indicators}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            logger.error(f"  - 错误详情: {str(e)}")
            raise RuntimeError(f"图表数据组装失败: {str(e)}") from e
    
    def _fetch_kline_data(self,
                         symbol: str,
                         period: str,
                         count: int,
                         before: Optional[pd.Timestamp],
                         market_local_time: pd.Timestamp) -> PriceData:
        """获取K线数据（DataProvider 已内置三层缓存）
        
        💚 DataProvider 自动处理:
        1. 内存缓存 → 毫秒级
        2. 数据库缓存 → 0.1-0.3秒
        3. 外部API → 4-8秒
        
        Args:
            symbol: 股票/指数代码
            period: 周期
            count: 数据条数
            before: 截止日期（pd.Timestamp 类型）
        
        Returns:
            PriceData: 强类型价格数据对象
        """
        # 🔧 无限滚动处理：根据周期调整 end_date
        if before:
            # 确保 before 带有正确的市场时区
            before = MarketTimeUtils.to_market_time_by_symbol(before, symbol)
            
            # before 已经是 pd.Timestamp 类型
            if period == 'monthly':
                # 月线：往前推1个月（避免重复返回同一个月的数据）
                # 例如：before=2021-01-31 → end_date=2020-12-31
                if before.month == 1:
                    end_date = pd.Timestamp(before.year - 1, 12, 31)
                else:
                    # 上个月的最后一天
                    end_date = pd.Timestamp(before.year, before.month, 1) - pd.Timedelta(days=1)
            elif period == 'weekly':
                # 周线：往前推7天
                end_date = before - pd.Timedelta(days=7)
            else:
                # 日线：往前推1天
                end_date = before - pd.Timedelta(days=1)
            logger.info(f"🔄 无限滚动：before={self._format_timestamp_safe(before)}, period={period}, end_date={self._format_timestamp_safe(end_date)}")
        else:
            # 初次加载：end_date = 今天（目标市场本地时间）
            end_date = MarketTimeUtils.get_market_time_now(symbol)
            # 确保 end_date 带有正确的市场时区
            end_date = MarketTimeUtils.to_market_time_by_symbol(end_date, symbol)
        
        # 🔧 根据周期调整查询范围，确保获取足够的数据点
        # 💡 关键：akshare等数据源可能限制历史数据范围，需要足够的冗余
        if period == 'monthly':
            # 🔧 关键修复：月线使用月份计算，不用天数估算
            # 从 end_date 往前推 count 个月
            from dateutil.relativedelta import relativedelta
            start_date = end_date - relativedelta(months=count)
            # 设置为月初，确保获取完整月份数据
            start_date = start_date.replace(day=1)
            logger.info(f"📅 月线查询范围：{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')} (共{count}个月)")
        elif period == 'weekly':
            # 周线：60条周线 = 420天，加冗余 → 800天
            days_needed = count * 14  # 增加到14天/条（原10天）
            start_date = end_date - pd.Timedelta(days=days_needed)
        else:
            # 日线：60条日线 = 60天，加冗余（周末/节假日）→ 120天
            days_needed = count * 2
            start_date = end_date - pd.Timedelta(days=days_needed)
        
        # 确保 start_date 带有正确的市场时区
        start_date = MarketTimeUtils.to_market_time_by_symbol(start_date, symbol)
        
        # 💚 直接调用 DataProvider，三层缓存已封装在内
        # 🔧 对于不支持直接查询的数据源（如 AKShare），会返回日线数据
        # 🔧 关键修复：传入 pd.Timestamp 类型（UTC时间）
        price_data = self._data_provider.get_index_prices(
            symbol,
            start_date,
            end_date,
            market_local_time,
            period  # 传递周期参数给数据源
        )
        
        # 🔧 关键修复：数据为空时直接返回，不抛异常（无限滚动到头是正常情况）
        if price_data is None or price_data.count == 0:
            logger.info(f"⚠️ 无数据：{symbol}，返回空 PriceData（可能是无限滚动到头）")
            # 返回空 PriceData 对象，而非抛异常
            # 🔧 使用目标市场时间
            market_now = MarketTimeUtils.get_market_time_now(symbol)
            # 确保 market_now 带有正确的市场时区
            market_now = MarketTimeUtils.to_market_time_by_symbol(market_now, symbol)
            
            return price_data if price_data else PriceData(
                records=[],
                symbol=symbol,
                start_date=market_now,
                end_date=market_now,
                count=0
            )
        
        logger.info(f"获取到 {price_data.count} 条数据，symbol={price_data.symbol}, 时间范围: {price_data.start_date} to {price_data.end_date}")
        
        return price_data
    
    def _slice_price_data(self, price_data: PriceData, start: int = 0, end: Optional[int] = None) -> PriceData:
        """裁剪 PriceData（保持强类型）
        
        Args:
            price_data: 原始价格数据
            start: 开始索引（支持负数）
            end: 结束索引（支持负数，None表示到最后）
        
        Returns:
            裁剪后的 PriceData 对象
        """
        if end is None:
            sliced_records = price_data.records[start:]
        else:
            sliced_records = price_data.records[start:end]
        
        return PriceData(
            records=sliced_records,
            symbol=price_data.symbol,
            start_date=sliced_records[0].date if sliced_records else price_data.start_date,
            end_date=sliced_records[-1].date if sliced_records else price_data.end_date,
            count=len(sliced_records)
        )
    
    def _calculate_indicators(self,
                             price_data: PriceData,
                             indicators: Optional[str]) -> tuple:
        """计算技术指标（使用强类型 PriceData）
        
        Args:
            price_data: K线数据（PriceData对象）
            indicators: 需要的指标（'all' 或逗号分隔）
        
        Returns:
            (kline_with_ma, indicators_data)
            - kline_with_ma: 包含MA的K线数据列表
            - indicators_data: 各指标数据字典
        """
        # 解析需要的指标
        if indicators == 'all':
            requested_indicators = ['vol', 'macd', 'rsi', 'kdj', 'obv']
        else:
            requested_indicators = [ind.strip().lower() for ind in (indicators or '').split(',') if ind.strip()]
        
        # 准备返回数据
        kline_data = []
        indicators_data = {}
        
        # 提取价格序列用于MA计算
        close_prices = pd.Series([r.close for r in price_data.records])
        ma5 = close_prices.rolling(window=5).mean()
        ma10 = close_prices.rolling(window=10).mean()
        ma20 = close_prices.rolling(window=20).mean()
        
        # 组装K线数据（包含MA）
        for i, record in enumerate(price_data.records):
            kline_record = {
                'date': self._format_timestamp_safe(record.date),
                'open': self._safe_float(record.open),
                'high': self._safe_float(record.high),
                'low': self._safe_float(record.low),
                'close': self._safe_float(record.close),
                'volume': self._safe_float(record.volume),
                'ma5': self._safe_float(ma5.iloc[i]),
                'ma10': self._safe_float(ma10.iloc[i]),
                'ma20': self._safe_float(ma20.iloc[i])
            }
            kline_data.append(kline_record)
        
        # 计算技术指标（调用领域层服务）
        if 'vol' in requested_indicators:
            indicators_data['vol'] = self._calculate_vol(price_data)
        
        if 'macd' in requested_indicators:
            indicators_data['macd'] = self._calculate_macd(price_data)
        
        if 'rsi' in requested_indicators:
            indicators_data['rsi'] = self._calculate_rsi(price_data)
        
        if 'kdj' in requested_indicators:
            indicators_data['kdj'] = self._calculate_kdj(price_data)
        
        if 'obv' in requested_indicators:
            indicators_data['obv'] = self._calculate_obv(price_data)
        
        return kline_data, indicators_data
    
    def _calculate_vol(self, price_data: PriceData) -> List[Dict]:
        """计算成交量指标（使用强类型 PriceData）"""
        return [
            {
                'date': self._format_timestamp_safe(record.date),
                'value': self._safe_float(record.volume)
            }
            for record in price_data.records
        ]
    
    def _calculate_macd(self, price_data: PriceData) -> List[Dict]:
        """计算MACD指标（调用领域层服务，使用强类型 PriceData）
        
        注意：
        - 使用Wilder EMA平滑法（pandas标准实现）
        - 前26个周期的值可能为NaN（需要足够数据才能计算）
        - 前端会自动处理null值，不显示对应点
        """
        try:
            logger.info(f"🔧 开始计算MACD，数据行数: {price_data.count}")
            
            # 提取价格序列（强类型 -> Series）
            close_prices = pd.Series([r.close for r in price_data.records])
            logger.info(f"   - close_prices 类型: {type(close_prices)}")
            logger.info(f"   - close_prices 前5个值: {close_prices.head().tolist()}")
            
            # 调用领域层服务计算MACD
            macd, signal, hist = self._indicator_service.calculate_macd(close_prices)
            
            logger.info(f"✅ MACD计算成功，返回类型: macd={type(macd)}, signal={type(signal)}, hist={type(hist)}")
            
            results = []
            for i, record in enumerate(price_data.records):
                # ⚠️ 关键：保留NaN转为null，让前端正确处理数据连续性
                results.append({
                    'date': self._format_timestamp_safe(record.date),
                    'macd': self._safe_float(macd.iloc[i] if hasattr(macd, 'iloc') else macd[i]),
                    'signal': self._safe_float(signal.iloc[i] if hasattr(signal, 'iloc') else signal[i]),
                    'histogram': self._safe_float(hist.iloc[i] if hasattr(hist, 'iloc') else hist[i])
                })
            
            logger.info(f"MACD计算成功：{len(results)}条数据，前{self._count_leading_nulls(results, 'macd')}条为null（正常）")
            logger.debug(f"MACD前3条数据: {results[:3]}")
            return results
        except Exception as e:
            logger.error(f"⚠️ MACD计算失败，返回空数据: {e}", exc_info=True)
            logger.error(f"   - price_data.count: {price_data.count}")
            logger.error(f"   - price_data.symbol: {price_data.symbol}")
            return []
    
    def _calculate_rsi(self, price_data: PriceData) -> List[Dict]:
        """计算RSI指标（调用领域层服务，使用强类型 PriceData）
        
        注意：
        - 使用Wilder平滑法（alpha=1/14）
        - 前14个周期的值可能为NaN
        - 返回值范围0-100
        """
        try:
            # 提取价格序列
            close_prices = pd.Series([r.close for r in price_data.records])
            rsi = self._indicator_service.calculate_rsi(close_prices)
            
            results = [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'value': self._safe_float(rsi.iloc[i] if hasattr(rsi, 'iloc') else rsi[i])
                }
                for i, record in enumerate(price_data.records)
            ]
            
            logger.debug(f"RSI计算完成：{len(results)}条数据，前{self._count_leading_nulls(results, 'value')}条为null（正常）")
            return results
        except Exception as e:
            logger.warning(f"RSI计算失败，返回空数据: {e}")
            return []
    
    def _calculate_kdj(self, price_data: PriceData) -> List[Dict]:
        """计算KDJ指标（调用领域层服务，使用强类型 PriceData）
        
        注意：
        - K线：随机指标（周期内价格相对位置）
        - D线：K线的3周期SMA平滑
        - J线：3*K - 2*D（灵敏指标）
        - 前9个周期的值可能为NaN
        """
        try:
            # 提取价格序列
            high_prices = pd.Series([r.high for r in price_data.records])
            low_prices = pd.Series([r.low for r in price_data.records])
            close_prices = pd.Series([r.close for r in price_data.records])
            
            k, d = self._indicator_service.calculate_kdj(
                high_prices,
                low_prices,
                close_prices
            )
            
            # 计算 J 值：J = 3*K - 2*D
            j = 3 * k - 2 * d
            
            results = [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'k': self._safe_float(k.iloc[i] if hasattr(k, 'iloc') else k[i]),
                    'd': self._safe_float(d.iloc[i] if hasattr(d, 'iloc') else d[i]),
                    'j': self._safe_float(j.iloc[i] if hasattr(j, 'iloc') else j[i])
                }
                for i, record in enumerate(price_data.records)
            ]
            return results
        except Exception as e:
            logger.warning(f"KDJ计算失败，返回空数据: {e}")
            return []
    
    def _calculate_obv(self, price_data: PriceData) -> List[Dict]:
        """计算OBV指标（调用领域层服务，使用强类型 PriceData）
        
        注意：
        - 能量潮指标，累计方向性成交量
        - 价格上涨日累加成交量，下跌日累减
        - 第一个值为0（起始点）
        """
        try:
            # 提取价格和成交量序列
            close_prices = pd.Series([r.close for r in price_data.records])
            volumes = pd.Series([r.volume for r in price_data.records])
            
            obv = self._indicator_service.calculate_obv(close_prices, volumes)
            
            results = [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'value': self._safe_float(obv.iloc[i] if hasattr(obv, 'iloc') else obv[i])
                }
                for i, record in enumerate(price_data.records)
            ]
            
            logger.debug(f"OBV计算完成：{len(results)}条数据")
            return results
        except Exception as e:
            logger.warning(f"OBV计算失败，返回空数据: {e}")
            return []
    
    def _calculate_chip_distribution(self, price_data: PriceData, bins: int = 50) -> Dict[str, Any]:
        """计算每个日期的累计筹码分布

        对每个日期 i，取 [0, i] 的累计 K 线数据，将每日成交量按价格区间均匀分布到 bins 中。
        返回: {date_str: {bins: [{price, volume, percentage}], minPrice, maxPrice, totalVolume}}
        """
        try:
            records = price_data.records
            if not records:
                return {}

            result = {}
            for i in range(len(records)):
                cumulative_records = records[:i + 1]

                global_min = min(r.low for r in cumulative_records)
                global_max = max(r.high for r in cumulative_records)
                total_volume = sum(r.volume for r in cumulative_records)

                if global_max <= global_min or total_volume == 0:
                    result[self._format_timestamp_safe(records[i].date)] = {
                        'bins': [],
                        'minPrice': self._safe_float(global_min),
                        'maxPrice': self._safe_float(global_max),
                        'totalVolume': 0,
                    }
                    continue

                bin_size = (global_max - global_min) / bins
                volumes = [0.0] * bins

                for r in cumulative_records:
                    day_range = r.high - r.low
                    if day_range == 0:
                        idx = min(int((r.close - global_min) / bin_size), bins - 1)
                        volumes[idx] += r.volume
                        continue

                    vol_per_unit = r.volume / day_range
                    start_idx = max(0, int((r.low - global_min) / bin_size))
                    end_idx = min(bins - 1, int((r.high - global_min) / bin_size))

                    for b in range(start_idx, end_idx + 1):
                        bin_low = global_min + b * bin_size
                        bin_high = global_min + (b + 1) * bin_size
                        overlap_low = max(r.low, bin_low)
                        overlap_high = min(r.high, bin_high)
                        overlap = max(0, overlap_high - overlap_low)
                        volumes[b] += overlap * vol_per_unit

                bin_data = []
                for b in range(bins):
                    price = global_min + (b + 0.5) * bin_size
                    vol = volumes[b]
                    percentage = (vol / total_volume * 100) if total_volume > 0 else 0
                    bin_data.append({
                        'price': self._safe_float(price),
                        'volume': self._safe_float(vol),
                        'percentage': self._safe_float(percentage),
                    })

                result[self._format_timestamp_safe(records[i].date)] = {
                    'bins': bin_data,
                    'minPrice': self._safe_float(global_min),
                    'maxPrice': self._safe_float(global_max),
                    'totalVolume': self._safe_float(total_volume),
                }

            return result
        except Exception as e:
            logger.warning(f"筹码分布计算失败: {e}", exc_info=True)
            return {}

    def _detect_events(self, price_data: PriceData) -> List[Dict]:
        """检测市场事件（暴涨暴跌）
        
        💚 强类型: 接收 PriceData 对象，不使用弱类型 DataFrame
        
        Args:
            price_data: K线价格数据（强类型）
        
        Returns:
            事件列表
        """
        events = []
        
        try:
            # 计算涨跌幅（使用强类型）
            if price_data.count < 2:
                return events
            
            records = price_data.records
            prev_close = None
            
            for i, record in enumerate(records):
                if prev_close is None:
                    prev_close = record.close
                    continue
                
                # 计算涨跌幅
                pct_change = ((record.close - prev_close) / prev_close) * 100
                
                if pct_change <= -5.0:
                    severity = 'critical' if pct_change < -7 else 'high'
                    events.append({
                        'date': self._format_timestamp_safe(record.date),
                        'type': 'market_crash',
                        'title': f'暴跌 {abs(pct_change):.2f}%',
                        'decline_pct': pct_change,
                        'price': float(record.close),
                        'impact': 'negative',
                        'severity': severity
                    })
                elif pct_change >= 5.0:
                    events.append({
                        'date': self._format_timestamp_safe(record.date),
                        'type': 'rally',
                        'title': f'暴涨 {pct_change:.2f}%',
                        'rise_pct': pct_change,
                        'price': float(record.close),
                        'impact': 'positive',
                        'severity': 'high'
                    })
                
                prev_close = record.close
        
        except Exception as e:
            logger.warning(f"事件检测失败: {e}")
        
        return events
    
    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """安全转换为float，处理NaN"""
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _format_timestamp_safe(timestamp) -> str:
        """安全格式化时间戳，避免NaT错误"""
        if timestamp is not pd.NaT and timestamp is not None and hasattr(timestamp, 'strftime'):
            return timestamp.strftime('%Y-%m-%d')
        else:
            return str(timestamp)
    
    @staticmethod
    def _count_leading_nulls(data: List[Dict], key: str) -> int:
        """统计列表开头有多少个null值"""
        count = 0
        for item in data:
            if item.get(key) is None:
                count += 1
            else:
                break
        return count
    
    def assemble_intraday_data(self, symbol: str, tick_range: Optional['TickRange'] = None) -> Dict[str, Any]:
        """
        组装分时图数据 - 仅负责真实数据
        
        Args:
            symbol: 证券代码
            tick_range: Tick数据时间范围（可选）
        
        Returns:
            {
                'symbol': str,
                'name': str,
                'current_price': float,
                'yesterday_close': float,
                'change': float,
                'change_percent': float,
                'times': List[str],
                'prices': List[float],
                'volumes': List[int],
                'avg_prices': List[float],
                'order_book': {
                    'bids': List[{'price': float, 'volume': int}],
                    'asks': List[{'price': float, 'volume': int}]
                },
                'trade_records': List[{'time': str, 'price': float, 'volume': int, 'type': str}],
                'should_poll': bool  # 🔧 是否应该轮询
            }
        """
        try:
            logger.info(f"开始组装分时数据: symbol={symbol}, tick_range={tick_range}")
            
            # 🔧 获取分时数据（调用DataProvider的get_intraday_data接口）
            # 重要：传递 tick_range 参数
            # - 首次加载（tick_range=None）：返回开盘到当前的全部数据
            # - 增量更新（tick_range有值）：只返回指定时间范围的增量数据
            intraday_data = self._data_provider.get_intraday_data(symbol, tick_range=tick_range)
            times = [tick.time for tick in intraday_data.ticks]
            prices = [tick.price for tick in intraday_data.ticks]
            volumes = [tick.volume for tick in intraday_data.ticks]
            avg_prices = [tick.avg_price for tick in intraday_data.ticks]
            
            order_book = {
                'bids': [{'price': level.price, 'volume': level.volume} 
                        for level in intraday_data.order_book_bids],
                'asks': [{'price': level.price, 'volume': level.volume} 
                        for level in intraday_data.order_book_asks],
                'message': intraday_data.order_book_message  # 🔧 添加后端提示信息
            }
            
            trade_records = [{
                'time': trade_record.time,
                'price': trade_record.price,
                'volume': trade_record.volume,
                'type': trade_record.direction
            } for trade_record in intraday_data.trade_records]
            
            # 🔧 如果tickers为空，添加message字段
            tickers_data = {
                'items': trade_records,
                'message': intraday_data.trade_records_message  # 🔧 添加后端提示信息
            }
            
            result = {
                'symbol': intraday_data.symbol,
                'name': intraday_data.name,
                'current_price': intraday_data.current_price,
                'yesterday_close': intraday_data.yesterday_close,
                'change': intraday_data.change,
                'change_percent': intraday_data.change_percent,
                'times': times,
                'prices': prices,
                'volumes': volumes,
                'avg_prices': avg_prices,
                'order_book': order_book,
                'trade_records': tickers_data,  # 🔧 使用新的tickers_data结构
                'is_index': intraday_data.is_index,  # 🔧 是否为指数（True=指数不可交易，False=个股可交易）
                'should_poll': intraday_data.should_poll  # 🔧 服务器根据 trading_phase 决定，前端只依赖此字段控制行为
            }
            
            logger.info(f"分时数据组装完成: times={len(times)}, order_book_bids={len(order_book['bids'])}, trade_records={len(trade_records)}")
            return result
        
        except ValueError as e:
            # 数据验证错误（如盘后数据不完整），直接向上抛出
            logger.warning(f"分时数据验证失败: {e}")
            raise  # 不要包装，直接抛出
        
        except Exception as e:
            logger.error(f"组装分时数据失败: {e}", exc_info=True)
            logger.error(f"  - symbol: {symbol}")
            logger.error(f"  - tick_range: {tick_range}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            logger.error(f"  - 错误详情: {str(e)}")
            raise RuntimeError(f"分时数据组装失败: {str(e)}") from e