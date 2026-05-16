# -*- coding: utf-8 -*-
"""
===================================
K线图数据接口
===================================

职责：
1. GET /api/v1/chart/data 获取K线+技术指标+事件数据
   供前端 kline_chart.js 调用
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
    → HistoryProviderAdapter（DataFrame → PriceData 转换）
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

        # 外部数据源：直接包装各底层 fetcher（不走 DataFetcherManager）
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

        # 实时数据组件（分时数据）
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


@router.get("/data")
def get_chart_data(
    symbol: str = Query(..., description="股票代码，如 600519, AAPL, HK00700"),
    period: str = Query("daily", description="K线周期: daily/weekly/monthly"),
    count: int = Query(120, ge=1, le=500, description="数据条数"),
    before: Optional[str] = Query(None, description="获取此日期之前的数据（YYYY-MM-DD，已获取的K线日期，可选）"),
    indicators: str = Query("all", description="指标列表，逗号分隔或 all"),
    realtime: bool = Query(True, description="是否启用实时K线更新（回测场景可设为 false）"),
):
    """
    获取K线图完整数据（K线 + 技术指标 + 事件）

    供前端 kline_chart.js 使用，返回格式与原始后端保持一致。
    """
    try:
        logger.info(f"[ChartAPI] 请求: symbol={symbol}, period={period}, count={count}, before={before}")

        assembler = _get_assembler()
        market_local_time = MarketTimeUtils.get_market_time_now(symbol)

        # 解析 before 参数（市场本地时间，无需额外时区转换）
        before_ts = None
        if before:
            try:
                before_ts = MarketTimeUtils.to_market_time_by_symbol(pd.Timestamp(before), symbol)
            except Exception as e:
                logger.warning(f"[ChartAPI] before 参数解析失败: {before}, error={e}")
                before_ts = None

        result = assembler.assemble_chart_data(
            symbol=symbol,
            period=period,
            count=count,
            before=before_ts,
            indicators=indicators,
            market_local_time=market_local_time,
            enable_realtime=realtime,
        )

        return {
            "status": "success",
            "data": result,
        }

    except Exception as e:
        logger.error(f"[ChartAPI] 获取图表数据失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "data": {
                "kline": [],
                "indicators": {},
                "events": [],
                "needs_realtime_kline": False,
            },
        }
