"""
HybridDataProvider — 方案C（BaseDataProvider三层缓存 + 分时/盘口/成交明细）为主体，
K线数据通过方案A（DataFetcherManager）多源轮询获取。

设计：
- 继承 market_chart 的 AKShareDataProvider（三层缓存/分时/盘口/成交明细全部复用）
- 仅覆盖 _fetch_history_kline_from_external_api → DataFetcherManager 多源轮询
- 覆盖 get_realtime_kline → 2参数版本，内部使用 DataFetcherManager

类型兼容性：
- market_chart 的 PriceData/OHLCVRecord 与 src/chart_legacy 的对应类型结构相同
- ChartDataAssembler 通过鸭子类型访问（.records, .symbol, .count, .open, .close 等）
- turnover_rate 通过 getattr 安全访问，无兼容性问题
"""

import sys
import os

# market_chart 模块的导入路径：需要将其 src 目录加入 sys.path
_market_chart_src = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'market_chart', 'markets', 'src'
)
if _market_chart_src not in sys.path:
    sys.path.insert(0, _market_chart_src)

import logging
from typing import Dict, Any, Optional

import pandas as pd

from core.data.providers.akshare_provider import AKShareDataProvider
from core.data.providers.protocols import PriceData
from core.share.market.market_time_utils import MarketTimeUtils
from core.share.market.market_enums import TradingPhase, MarketCode
from core.share.market import MarketUtils

logger = logging.getLogger(__name__)


class HybridDataProvider(AKShareDataProvider):
    """方案C + 方案A 混合数据提供者

    K线历史数据走 DataFetcherManager 多源轮询（方案A），
    分时/盘口/成交明细继承 AKShareDataProvider 实现（方案C）。
    缓存使用 BaseDataProvider 自带的 ThreeLayerCacheManager。
    """

    def __init__(self, fetcher_manager=None, bar_repository=None):
        """初始化混合提供者

        Args:
            fetcher_manager: DataFetcherManager 实例（方案A多源轮询）。
                             不提供时自动创建默认实例。
            bar_repository: 可选的 SqliteBarRepository 实例（方案B数据库访问层）。
                            提供时启用 SQLite 持久化读写。
        """
        super().__init__(db_repository=bar_repository)

        if fetcher_manager is None:
            from data_provider.base import DataFetcherManager
            fetcher_manager = DataFetcherManager()
        self._fetcher_manager = fetcher_manager

        logger.info("HybridDataProvider 已初始化: K线=多源轮询, 分时=AKShare, 缓存=三层缓存+DB持久化")

    # === 核心覆盖：历史K线走多源轮询 ===

    def _fetch_history_kline_from_external_api(
        self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str = 'daily'
    ) -> PriceData:
        """通过 DataFetcherManager 多源轮询获取历史K线数据

        替代 AKShareDataProvider 的单源 AKShare 调用，
        改为走 DataFetcherManager 的多数据源故障切换链路。
        """
        start_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
        end_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date)

        try:
            logger.info(f"[Hybrid] 多源轮询获取: {symbol}, {start_str} ~ {end_str}")
            df, source_name = self._fetcher_manager.get_daily_data(
                stock_code=symbol,
                start_date=start_str,
                end_date=end_str,
            )

            if df is None or df.empty:
                logger.warning(f"[Hybrid] {symbol} 所有数据源均无数据")
                return PriceData(
                    records=[],
                    symbol=symbol,
                    start_date=pd.Timestamp(start_str),
                    end_date=pd.Timestamp(end_str),
                    count=0,
                )

            logger.info(f"[Hybrid] {symbol} 获取成功: {len(df)} 条 (来源: {source_name})")

            return PriceData.from_dataframe(df, symbol)

        except Exception as e:
            logger.error(f"[Hybrid] 多源轮询失败 {symbol}: {e}")
            return PriceData(
                records=[],
                symbol=symbol,
                start_date=pd.Timestamp(start_str),
                end_date=pd.Timestamp(end_str),
                count=0,
            )

    # === 覆盖：实时K线 2参数版本 ===

    def get_realtime_kline(self, symbol: str, period: str = 'daily') -> Dict[str, Any]:
        """获取实时K线数据（2参数版本，供 realtime.py 使用）

        使用 DataFetcherManager.get_realtime_quote() 获取当日实时行情，
        组装为当日K柱。周线/月线合并到最后一个周期K柱。

        Returns:
            {
                'date': str,
                'open': float | None, 'high': float | None,
                'low': float | None, 'close': float | None,
                'volume': int, 'turnover_rate': float | None,
                'trading_phase': str, 'should_poll': bool,
            }
        """
        market_local_time = MarketTimeUtils.get_market_time_now(symbol)
        market = MarketUtils.infer_market_from_symbol(symbol)
        market_code = MarketCode.parse(market.value.upper() if hasattr(market, 'value') else 'CN')
        trading_phase = MarketTimeUtils.determine_trading_phase(market_code, market_local_time)
        trade_date = market_local_time.strftime('%Y-%m-%d')

        if trading_phase == TradingPhase.AFTER_CLOSE:
            return {
                'date': trade_date,
                'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0,
                'turnover_rate': None,
                'trading_phase': trading_phase.value,
                'should_poll': False,
            }

        quote = self._fetcher_manager.get_realtime_quote(symbol)
        if quote is None or not quote.has_basic_data():
            logger.warning(f"[Hybrid] 无法获取 {symbol} 实时行情")
            return {
                'date': trade_date,
                'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0,
                'turnover_rate': None,
                'trading_phase': trading_phase.value,
                'should_poll': True,
            }

        kline = {
            'date': trade_date,
            'open': quote.open_price,
            'high': quote.high,
            'low': quote.low,
            'close': quote.price,
            'volume': quote.volume or 0,
            'turnover_rate': quote.turnover_rate,
            'trading_phase': trading_phase.value,
            'should_poll': True,
        }

        if period in ('weekly', 'monthly'):
            kline = self._merge_realtime_to_period(symbol, period, kline)

        return kline

    def _merge_realtime_to_period(self, symbol: str, period: str, realtime_kline: Dict[str, Any]) -> Dict[str, Any]:
        """将当日实时K线合并到周线/月线的最后一个K柱"""
        cache_key = f"last_period_bar_{symbol}_{period}"
        last_bar = self._get_from_memory_cache(cache_key)

        if not last_bar:
            logger.warning(f"[Hybrid] {period}线缓存未命中，查询历史数据")
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
                    self._set_to_memory_cache_obj(cache_key, last_bar)
                else:
                    return realtime_kline
            except Exception as e:
                logger.warning(f"[Hybrid] 查询历史数据失败: {e}，返回原始实时K线")
                return realtime_kline

        realtime_date = pd.Timestamp(realtime_kline['date'])
        last_date = pd.Timestamp(last_bar['date'])

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
            logger.info(f"[Hybrid] {period}线 - 创建新K柱: {realtime_kline['date']}")
            return realtime_kline

        logger.info(f"[Hybrid] {period}线 - 合并K柱: {last_bar['date']} <- {realtime_kline['date']}")
        return {
            'date': last_bar['date'],
            'open': last_bar['open'],
            'high': max(last_bar['high'], realtime_kline['high'] or last_bar['high']),
            'low': min(last_bar['low'], realtime_kline['low'] or last_bar['low']),
            'close': realtime_kline['close'],
            'volume': (last_bar.get('volume', 0) or 0) + (realtime_kline.get('volume', 0) or 0),
            'turnover_rate': realtime_kline.get('turnover_rate'),
            'trading_phase': realtime_kline['trading_phase'],
            'should_poll': realtime_kline['should_poll'],
        }
