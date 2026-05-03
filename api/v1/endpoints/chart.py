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
from src.chart_legacy.data_provider_adapter import DataFetcherAdapter
from src.chart_legacy.indicator_service import TechnicalIndicators
from src.chart_legacy.market_time_utils import MarketTimeUtils

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局单例（延迟初始化）
_assembler: Optional[ChartDataAssembler] = None


def _get_assembler() -> ChartDataAssembler:
    """获取或创建 ChartDataAssembler 单例"""
    global _assembler
    if _assembler is None:
        data_provider = DataFetcherAdapter()
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
