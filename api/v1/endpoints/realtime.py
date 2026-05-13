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

from fastapi import APIRouter, Query

from src.chart_legacy.chart_data_assembler import ChartDataAssembler
from src.chart_legacy.indicator_service import TechnicalIndicators
from src.chart_legacy.market_time_utils import MarketTimeUtils
from src.data_provider.hybrid_provider import HybridDataProvider

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局单例（延迟初始化）
_assembler: Optional[ChartDataAssembler] = None


def _get_assembler() -> ChartDataAssembler:
    """获取或创建 ChartDataAssembler 单例

    数据链路：HybridDataProvider（方案C三层缓存 + 方案A多源轮询K线）
    → ChartDataAssembler（指标计算 + 筹码分布 + 事件检测）
    """
    global _assembler
    if _assembler is None:
        data_provider = HybridDataProvider()
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
