# -*- coding: utf-8 -*-
"""
===================================
实时K线数据接口
===================================

职责：
1. GET /api/v1/data/kline/realtime 获取实时K线柱数据
   供前端 kline_chart.js 的 fetchRealtimeKline() 调用

设计：
- 盘中：返回当日实时K柱（open/high/low/close/volume）
- 盘前：返回集合竞价参考价格（should_poll=true）
- 盘后：返回空数据（should_poll=false，停止轮询）
- 周线/月线：后端合并当日数据到最后一个周期K柱
"""

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from src.chart_legacy.chart_data_assembler import ChartDataAssembler
from src.chart_legacy.indicator_service import TechnicalIndicators
from src.chart_legacy.market_time_utils import MarketTimeUtils
from src.data_provider.bar_repository import SqliteBarRepository
from src.data_provider.trading_calendar_adapter import XCalTradingCalendar
from core.data.history_provider.memory_provider import MemoryCacheProvider
from core.data.history_provider.db_provider import DbProvider
from core.data.history_provider.external_provider import ExternalApiProvider
from core.data.history_provider.multi_source import MultiSourceProvider
from core.data.history_provider.three_layer import ThreeLayerProvider
from src.history_provider.adapter import HistoryProviderAdapter, DataFetcherManagerQuoteFetcher
from core.data.realtime_provider import IntradayProvider
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局单例（延迟初始化）
_assembler: Optional[ChartDataAssembler] = None


def _get_assembler() -> ChartDataAssembler:
    """获取或创建 ChartDataAssembler 单例

    数据链路：ThreeLayerProvider（Memory → DB → MultiSource）
    → HistoryProviderAdapter（DataFrame → PriceData 转换 + 实时K线）
    → ChartDataAssembler（指标计算 + 筹码分布 + 事件检测）
    """
    global _assembler
    if _assembler is None:
        calendar = XCalTradingCalendar(market="cn")
        bar_repo = SqliteBarRepository(
            db_manager=DatabaseManager.get_instance(),
            calendar=calendar,
        )

        # 三层缓存体系
        memory = MemoryCacheProvider()
        db = DbProvider(repository=bar_repo)

        # 外部数据源：直接包装各底层 fetcher
        from data_provider.base import DataFetcherManager

        fetcher_mgr = DataFetcherManager()
        fetchers = fetcher_mgr._get_fetchers_snapshot()

        def _make_adapter(fetcher):
            """将 BaseFetcher 适配为 ExternalApiProvider 的接口"""
            def adapter(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
                df = fetcher.get_daily_data(
                    stock_code=symbol,
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                )
                return df if df is not None and not df.empty else None
            return adapter

        ext_providers = [
            ExternalApiProvider(name=f.name, fetcher=_make_adapter(f))
            for f in fetchers
        ]
        multi_source = MultiSourceProvider(providers=ext_providers)

        three_layer = ThreeLayerProvider(
            memory=memory,
            db=db,
            multi_source=multi_source,
            calendar=calendar,
        )

        # 实时数据组件
        quote_fetcher = DataFetcherManagerQuoteFetcher(fetcher_mgr)
        intraday_provider = IntradayProvider(quote_fetcher=quote_fetcher)

        data_provider = HistoryProviderAdapter(
            history_provider=three_layer,
            intraday_provider=intraday_provider,
        )

        indicator_service = TechnicalIndicators(market='CN', timeframe='daily')
        _assembler = ChartDataAssembler(
            data_provider=data_provider,
            indicator_service=indicator_service,
        )
    return _assembler


@router.get("/kline/realtime")
def get_realtime_kline(
    symbol: str = Query(..., description="股票代码，如 600519, AAPL, HK00700"),
    period: str = Query("daily", description="K线周期: daily/weekly/monthly"),
):
    """
    获取实时K线柱数据

    供前端 kline_chart.js 使用，返回当日实时K柱。
    周线/月线已合并当日数据到最后一个周期K柱。
    """
    try:
        logger.info(f"[RealtimeAPI] 请求: symbol={symbol}, period={period}")

        assembler = _get_assembler()
        result = assembler._data_provider.get_realtime_kline(symbol, period)

        return {
            "status": "success",
            "data": result,
            "timestamp": MarketTimeUtils.get_market_time_now(symbol).isoformat(),
        }

    except Exception as e:
        logger.error(f"[RealtimeAPI] 获取实时K线失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "data": {
                "date": None,
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume": 0,
                "should_poll": False,
            },
        }
