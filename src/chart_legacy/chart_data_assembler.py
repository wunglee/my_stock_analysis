"""图表数据组装模块

从 market_chart/markets/src/app/chart_data.py 整包移植
仅调整导入路径，保持原始逻辑不变。
"""

import logging
from typing import Dict, Any, List, Optional

import pandas as pd

from src.chart_legacy.market_types import PriceData, TickRange
from src.chart_legacy.market_time_utils import MarketTimeUtils

logger = logging.getLogger('chart_legacy.ChartDataAssembler')


class ChartDataAssembler:
    """图表数据组装器"""

    def __init__(self, data_provider: Any, indicator_service: Any) -> None:
        self._data_provider = data_provider
        self._indicator_service = indicator_service

    def assemble_chart_data(
        self,
        symbol: str,
        period: str = 'daily',
        count: int = 120,
        before: Optional[pd.Timestamp] = None,
        indicators: Optional[str] = 'all',
        market_local_time: pd.Timestamp = None,
    ) -> Dict[str, Any]:
        """组装完整的图表数据"""
        try:
            if market_local_time is None:
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)
            market_local_time = MarketTimeUtils.to_market_time_by_symbol(market_local_time, symbol)

            logger.info(f"开始组装图表数据: symbol={symbol}, period={period}, count={count}")

            # 1. 获取K线数据
            if period == 'monthly':
                warmup_count = 3
            elif period == 'weekly':
                warmup_count = 10
            else:
                warmup_count = 30
            price_data_full = self._fetch_kline_data(symbol, period, count + warmup_count, before, market_local_time)

            if price_data_full is None or price_data_full.count == 0:
                logger.info(f"无数据：{symbol}，返回空结果")
                return {
                    'kline': [],
                    'indicators': {},
                    'events': [],
                    'needs_realtime_kline': False,
                }

            logger.info(f"K线数据获取成功，共 {price_data_full.count} 条")

            # 交易时段排除最后一个K柱
            exclude_last_bar = price_data_full.needs_realtime_kline
            last_bar_for_cache = None

            if exclude_last_bar:
                logger.info(f"交易时段，排除最后一个{period}周期K柱")
                price_data_for_calculation = self._slice_price_data(price_data_full, 0, -1)
                if period in ['weekly', 'monthly'] and price_data_full.count > 0:
                    last_record = price_data_full.records[-1]
                    last_bar_for_cache = {
                        'date': last_record.date.strftime('%Y-%m-%d'),
                        'open': float(last_record.open),
                        'high': float(last_record.high),
                        'low': float(last_record.low),
                        'close': float(last_record.close),
                        'volume': int(last_record.volume),
                    }
                    cache_key = f"last_period_bar_{symbol}_{period}"
                    self._data_provider._set_to_memory_cache_obj(cache_key, last_bar_for_cache)
            else:
                price_data_for_calculation = price_data_full

            # 2. 计算技术指标
            logger.info(f"步骤2: 计算技术指标 ({indicators})...")
            kline_with_ma_full, indicators_data_full = self._calculate_indicators(price_data_for_calculation, indicators)

            # 裁剪掉预热数据
            kline_with_ma = kline_with_ma_full[-count:] if len(kline_with_ma_full) > count else kline_with_ma_full
            indicators_data = {
                key: value[-count:] if len(value) > count else value
                for key, value in indicators_data_full.items()
            }

            # 3. 检测市场事件
            logger.info("步骤3: 检测市场事件...")
            price_data_requested = self._slice_price_data(price_data_for_calculation, -count, None)
            events = self._detect_events(price_data_requested)

            # 4. 计算筹码分布
            logger.info("步骤4: 计算筹码分布...")
            chip_distribution = self._calculate_chip_distribution(price_data_requested)

            # 5. 组装返回
            result = {
                'kline': kline_with_ma,
                'indicators': indicators_data,
                'events': events,
                'chipDistribution': chip_distribution,
                'needs_realtime_kline': price_data_full.needs_realtime_kline,
            }
            logger.info(
                f"图表数据组装完成: kline={len(kline_with_ma)} 条, "
                f"indicators={len(indicators_data)} 个, events={len(events)} 个"
            )
            return result

        except Exception as e:
            logger.error(f"组装图表数据失败: {e}", exc_info=True)
            raise RuntimeError(f"图表数据组装失败: {str(e)}") from e

    def _fetch_kline_data(
        self,
        symbol: str,
        period: str,
        count: int,
        before: Optional[pd.Timestamp],
        market_local_time: pd.Timestamp,
    ) -> PriceData:
        """获取K线数据"""
        if before:
            before = MarketTimeUtils.to_market_time_by_symbol(before, symbol)
            if period == 'monthly':
                if before.month == 1:
                    end_date = pd.Timestamp(before.year - 1, 12, 31)
                else:
                    end_date = pd.Timestamp(before.year, before.month, 1) - pd.Timedelta(days=1)
            elif period == 'weekly':
                end_date = before - pd.Timedelta(days=7)
            else:
                end_date = before - pd.Timedelta(days=1)
        else:
            end_date = MarketTimeUtils.get_market_time_now(symbol)
            end_date = MarketTimeUtils.to_market_time_by_symbol(end_date, symbol)

        if period == 'monthly':
            from dateutil.relativedelta import relativedelta
            start_date = end_date - relativedelta(months=count)
            start_date = start_date.replace(day=1)
        elif period == 'weekly':
            days_needed = count * 14
            start_date = end_date - pd.Timedelta(days=days_needed)
        else:
            days_needed = count * 2
            start_date = end_date - pd.Timedelta(days=days_needed)

        start_date = MarketTimeUtils.to_market_time_by_symbol(start_date, symbol)

        price_data = self._data_provider.get_index_prices(
            symbol, start_date, end_date, market_local_time, period
        )

        if price_data is None or price_data.count == 0:
            market_now = MarketTimeUtils.get_market_time_now(symbol)
            market_now = MarketTimeUtils.to_market_time_by_symbol(market_now, symbol)
            return price_data if price_data else PriceData(
                records=[], symbol=symbol, start_date=market_now, end_date=market_now, count=0
            )

        return price_data

    def _slice_price_data(self, price_data: PriceData, start: int = 0, end: Optional[int] = None) -> PriceData:
        """裁剪 PriceData"""
        if end is None:
            sliced_records = price_data.records[start:]
        else:
            sliced_records = price_data.records[start:end]
        return PriceData(
            records=sliced_records,
            symbol=price_data.symbol,
            start_date=sliced_records[0].date if sliced_records else price_data.start_date,
            end_date=sliced_records[-1].date if sliced_records else price_data.end_date,
            count=len(sliced_records),
        )

    def _calculate_indicators(
        self, price_data: PriceData, indicators: Optional[str]
    ) -> tuple:
        """计算技术指标"""
        if indicators == 'all':
            requested_indicators = ['vol', 'macd', 'rsi', 'kdj', 'obv']
        else:
            requested_indicators = [ind.strip().lower() for ind in (indicators or '').split(',') if ind.strip()]

        kline_data = []
        indicators_data = {}

        close_prices = pd.Series([r.close for r in price_data.records])
        ma5 = close_prices.rolling(window=5).mean()
        ma10 = close_prices.rolling(window=10).mean()
        ma20 = close_prices.rolling(window=20).mean()

        for i, record in enumerate(price_data.records):
            kline_record = {
                'date': self._format_timestamp_safe(record.date),
                'open': self._safe_float(record.open),
                'high': self._safe_float(record.high),
                'low': self._safe_float(record.low),
                'close': self._safe_float(record.close),
                'volume': self._safe_float(record.volume),
                'turnover_rate': self._safe_float(record.turnover_rate) if record.turnover_rate is not None else None,
                'ma5': self._safe_float(ma5.iloc[i]),
                'ma10': self._safe_float(ma10.iloc[i]),
                'ma20': self._safe_float(ma20.iloc[i]),
            }
            kline_data.append(kline_record)

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
        return [
            {'date': self._format_timestamp_safe(record.date), 'value': self._safe_float(record.volume)}
            for record in price_data.records
        ]

    def _calculate_macd(self, price_data: PriceData) -> List[Dict]:
        try:
            close_prices = pd.Series([r.close for r in price_data.records])
            macd, signal, hist = self._indicator_service.calculate_macd(close_prices)
            return [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'macd': self._safe_float(macd.iloc[i] if hasattr(macd, 'iloc') else macd[i]),
                    'signal': self._safe_float(signal.iloc[i] if hasattr(signal, 'iloc') else signal[i]),
                    'histogram': self._safe_float(hist.iloc[i] if hasattr(hist, 'iloc') else hist[i]),
                }
                for i, record in enumerate(price_data.records)
            ]
        except Exception as e:
            logger.warning(f"MACD计算失败: {e}")
            return []

    def _calculate_rsi(self, price_data: PriceData) -> List[Dict]:
        try:
            close_prices = pd.Series([r.close for r in price_data.records])
            rsi = self._indicator_service.calculate_rsi(close_prices)
            return [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'value': self._safe_float(rsi.iloc[i] if hasattr(rsi, 'iloc') else rsi[i]),
                }
                for i, record in enumerate(price_data.records)
            ]
        except Exception as e:
            logger.warning(f"RSI计算失败: {e}")
            return []

    def _calculate_kdj(self, price_data: PriceData) -> List[Dict]:
        try:
            high_prices = pd.Series([r.high for r in price_data.records])
            low_prices = pd.Series([r.low for r in price_data.records])
            close_prices = pd.Series([r.close for r in price_data.records])
            k, d = self._indicator_service.calculate_kdj(high_prices, low_prices, close_prices)
            j = 3 * k - 2 * d
            return [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'k': self._safe_float(k.iloc[i] if hasattr(k, 'iloc') else k[i]),
                    'd': self._safe_float(d.iloc[i] if hasattr(d, 'iloc') else d[i]),
                    'j': self._safe_float(j.iloc[i] if hasattr(j, 'iloc') else j[i]),
                }
                for i, record in enumerate(price_data.records)
            ]
        except Exception as e:
            logger.warning(f"KDJ计算失败: {e}")
            return []

    def _calculate_obv(self, price_data: PriceData) -> List[Dict]:
        try:
            close_prices = pd.Series([r.close for r in price_data.records])
            volumes = pd.Series([r.volume for r in price_data.records])
            obv = self._indicator_service.calculate_obv(close_prices, volumes)
            return [
                {
                    'date': self._format_timestamp_safe(record.date),
                    'value': self._safe_float(obv.iloc[i] if hasattr(obv, 'iloc') else obv[i]),
                }
                for i, record in enumerate(price_data.records)
            ]
        except Exception as e:
            logger.warning(f"OBV计算失败: {e}")
            return []

    def _calculate_chip_distribution(self, price_data: PriceData, bins: int = 50) -> Dict[str, Any]:
        """使用换手率衰减模型计算专业筹码分布 (CYQ)

        核心逻辑：
        1. 历史筹码每日按换手率衰减：chips *= (1 - turnover_rate/100)
        2. 当日新成交量均匀分布到当日价格区间（high-low）
        3. 交易区间外的筹码只会因衰减而减少，不会增加

        返回: {date_str: {bins: [{price, volume, percentage}], minPrice, maxPrice, totalVolume}}
        """
        try:
            records = price_data.records
            if not records:
                return {}

            all_time_min = min(r.low for r in records)
            all_time_max = max(r.high for r in records)

            if all_time_max <= all_time_min:
                return {}

            price_range = all_time_max - all_time_min
            bin_size = price_range / bins

            # 检测是否有换手率数据
            has_turnover = any(
                getattr(r, 'turnover_rate', 0) is not None and getattr(r, 'turnover_rate', 0) > 0
                for r in records
            )
            if not has_turnover:
                logger.warning("[筹码分布] 无换手率数据，使用默认衰减率 2%/日")

            # 累计筹码数组（每个 bin 的筹码量）
            cumulative_volumes = [0.0] * bins
            result = {}

            for i, r in enumerate(records):
                # 1. 历史筹码衰减
                turnover_rate = getattr(r, 'turnover_rate', None)
                if turnover_rate is not None and turnover_rate > 0:
                    decay_factor = max(0.0, 1.0 - turnover_rate / 100.0)
                elif turnover_rate == 0:
                    # 明确为0（停牌）：不衰减
                    decay_factor = 1.0
                else:
                    # 无换手率数据时使用默认衰减率（约50个交易日完全置换）
                    decay_factor = 0.98

                # 记录衰减前的状态，用于诊断
                volumes_before = cumulative_volumes.copy()

                for b in range(bins):
                    cumulative_volumes[b] *= decay_factor

                # 2. 当日新筹码分布到 high-low 区间
                day_range = r.high - r.low
                if day_range == 0:
                    # 一字板：全部归入 close 所在的 bin
                    idx = min(int((r.close - all_time_min) / bin_size), bins - 1)
                    cumulative_volumes[idx] += r.volume
                else:
                    vol_per_unit = r.volume / day_range
                    start_idx = max(0, int((r.low - all_time_min) / bin_size))
                    end_idx = min(bins - 1, int((r.high - all_time_min) / bin_size))

                    for b in range(start_idx, end_idx + 1):
                        bin_low = all_time_min + b * bin_size
                        bin_high = all_time_min + (b + 1) * bin_size
                        overlap_low = max(r.low, bin_low)
                        overlap_high = min(r.high, bin_high)
                        overlap = max(0.0, overlap_high - overlap_low)
                        cumulative_volumes[b] += overlap * vol_per_unit

                # 诊断：检查是否有交易区间外的bin筹码增加（这不应该发生）
                if day_range > 0:
                    for b in range(bins):
                        bin_low = all_time_min + b * bin_size
                        bin_high = all_time_min + (b + 1) * bin_size
                        # bin与交易区间严格无交集
                        no_overlap = bin_high <= r.low or bin_low >= r.high
                        if no_overlap and cumulative_volumes[b] > volumes_before[b]:
                            logger.error(
                                f"[筹码BUG] {r.date} bin={b} ({bin_low:.2f}-{bin_high:.2f}) "
                                f"在交易区间({r.low:.2f}-{r.high:.2f})外却增加了: "
                                f"{volumes_before[b]:.1f} -> {cumulative_volumes[b]:.1f}"
                            )

                # 4. 构建结果
                total_volume = sum(cumulative_volumes)
                bin_data = []
                for b in range(bins):
                    price = all_time_min + (b + 0.5) * bin_size
                    vol = cumulative_volumes[b]
                    percentage = (vol / total_volume * 100) if total_volume > 0 else 0
                    bin_data.append({
                        'price': self._safe_float(price),
                        'volume': self._safe_float(vol),
                        'percentage': self._safe_float(percentage),
                    })

                # 筹码统计信息
                current_close = r.close
                avg_cost = sum(b['price'] * b['volume'] for b in bin_data) / total_volume if total_volume > 0 else 0
                profit_volume = sum(b['volume'] for b in bin_data if b['price'] < current_close)
                loss_volume = sum(b['volume'] for b in bin_data if b['price'] >= current_close)
                profit_ratio = (profit_volume / total_volume * 100) if total_volume > 0 else 0
                loss_ratio = (loss_volume / total_volume * 100) if total_volume > 0 else 0
                profit_loss_ratio = (profit_volume / loss_volume) if loss_volume > 0 else float('inf')

                result[self._format_timestamp_safe(r.date)] = {
                    'bins': bin_data,
                    'minPrice': self._safe_float(all_time_min),
                    'maxPrice': self._safe_float(all_time_max),
                    'totalVolume': self._safe_float(total_volume),
                    'avgCost': self._safe_float(avg_cost),
                    'profitVolume': self._safe_float(profit_volume),
                    'lossVolume': self._safe_float(loss_volume),
                    'profitRatio': self._safe_float(profit_ratio),
                    'lossRatio': self._safe_float(loss_ratio),
                    'profitLossRatio': self._safe_float(profit_loss_ratio if profit_loss_ratio != float('inf') else None),
                }

            return result
        except Exception as e:
            logger.warning(f"筹码分布计算失败: {e}", exc_info=True)
            return {}

    def _detect_events(self, price_data: PriceData) -> List[Dict]:
        events = []
        try:
            if price_data.count < 2:
                return events
            records = price_data.records
            prev_close = None
            for record in records:
                if prev_close is None:
                    prev_close = record.close
                    continue
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
                        'severity': severity,
                    })
                elif pct_change >= 5.0:
                    events.append({
                        'date': self._format_timestamp_safe(record.date),
                        'type': 'rally',
                        'title': f'暴涨 {pct_change:.2f}%',
                        'rise_pct': pct_change,
                        'price': float(record.close),
                        'impact': 'positive',
                        'severity': 'high',
                    })
                prev_close = record.close
        except Exception as e:
            logger.warning(f"事件检测失败: {e}")
        return events

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _format_timestamp_safe(timestamp) -> str:
        if timestamp is not pd.NaT and timestamp is not None and hasattr(timestamp, 'strftime'):
            return timestamp.strftime('%Y-%m-%d')
        else:
            return str(timestamp)

    def assemble_intraday_data(self, symbol: str, tick_range: Optional[TickRange] = None) -> Dict[str, Any]:
        """组装分时图数据 - 仅负责真实数据"""
        try:
            logger.info(f"开始组装分时数据: symbol={symbol}, tick_range={tick_range}")

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
                'message': intraday_data.order_book_message,
            }

            trade_records = [{
                'time': trade_record.time,
                'price': trade_record.price,
                'volume': trade_record.volume,
                'type': trade_record.direction,
            } for trade_record in intraday_data.trade_records]

            tickers_data = {
                'items': trade_records,
                'message': intraday_data.trade_records_message,
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
                'trade_records': tickers_data,
                'is_index': intraday_data.is_index,
                'should_poll': intraday_data.should_poll,
            }

            logger.info(f"分时数据组装完成: times={len(times)}, order_book_bids={len(order_book['bids'])}, trade_records={len(trade_records)}")
            return result

        except ValueError as e:
            logger.warning(f"分时数据验证失败: {e}")
            raise

        except Exception as e:
            logger.error(f"组装分时数据失败: {e}", exc_info=True)
            logger.error(f"  - symbol: {symbol}")
            logger.error(f"  - tick_range: {tick_range}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            logger.error(f"  - 错误详情: {str(e)}")
            raise RuntimeError(f"分时数据组装失败: {str(e)}") from e
