# -*- coding: utf-8 -*-
"""技术回测端点（V2 批量回测）

独立的 router 文件，与 AI 回测端点（backtest.py）隔离。
"""

from __future__ import annotations

import dataclasses
import logging
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.backtest import (
    StrategyConfigItem,
    StrategyListResponse,
    TechnicalBacktestRequest,
    TechnicalBacktestResponse,
    TechnicalBatchRequest,
    TechnicalBatchResponse,
    TemplateItem,
    TemplateListResponse,
    TemplateSaveRequest,
    SessionSaveRequest,
    SessionItem,
)
from api.v1.schemas.common import ErrorResponse
from src.config import get_config
from src.data_provider.bar_repository import SqliteBarRepository
from src.data_provider.caching_provider import CachingDataProvider
from src.data_provider.external_data_source import FetcherManagerDataSource
from src.data_provider.trading_calendar_adapter import XCalTradingCalendar
from src.services.backtest.engine.data_adapter import CachingDataProviderAdapter
from src.services.backtest.engine.equity_calculator import TradingCalendar
from src.services.backtest.service import TechnicalBacktestService as V2BacktestService
from src.services.backtest.strategies.registry import get_default_registry
from src.services.technical_backtest_service import TechnicalBacktestService
from src.storage import DatabaseManager
from src.repositories.backtest_template_repo import BacktestTemplateRepository
from src.repositories.backtest_session_repo import BacktestSessionRepository
from data_provider.base import DataFetcherManager

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache(maxsize=1)
def _get_cached_calendar() -> XCalTradingCalendar:
    """缓存交易日历（无状态，进程级复用）"""
    return XCalTradingCalendar(market="cn")


def _require_technical_backtest_enabled() -> None:
    """功能开关守卫：在昂贵依赖解析前短路，避免浪费数据库连接等资源"""
    if not get_config().technical_backtest_enabled:
        raise HTTPException(status_code=503, detail="技术回测功能已禁用")


def _make_calendar_adapter(xcal: XCalTradingCalendar) -> TradingCalendar:
    """将 XCalTradingCalendar 适配为 TradingCalendar Protocol (pd.Timestamp)"""

    class _Adapter:
        def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
            ts = date.tz_localize(xcal.tz) if date.tz is None else date.tz_convert(xcal.tz)
            return xcal.next_trading_day(ts)

        def is_trading_day(self, date: pd.Timestamp) -> bool:
            ts = date.tz_localize(xcal.tz) if date.tz is None else date.tz_convert(xcal.tz)
            return xcal.is_trading_day(ts)

    return _Adapter()


def get_v2_backtest_service(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> V2BacktestService:
    """获取 V2 批量回测服务实例（依赖注入）

    注意：CachingDataProvider 依赖 db_manager（请求级数据库连接），
    因此无法进程级缓存，每请求重建。registry 和 calendar 已缓存。
    """
    registry = get_default_registry()
    calendar = _get_cached_calendar()
    bar_repo = SqliteBarRepository(db_manager=db_manager, calendar=calendar)
    ext_source = FetcherManagerDataSource(DataFetcherManager())
    provider = CachingDataProvider(
        repository=bar_repo,
        external_source=ext_source,
        calendar=calendar,
    )
    fetcher = CachingDataProviderAdapter(provider)
    trading_calendar = _make_calendar_adapter(calendar)
    return V2BacktestService(registry, fetcher, calendar=trading_calendar)


@router.post(
    "/technical",
    response_model=TechnicalBacktestResponse,
    responses={
        200: {"description": "纯技术回测完成"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="纯技术回测",
    description="基于真实K线数据计算技术指标并生成交易信号，不依赖AI分析结果",
)
def run_technical_backtest(
    request: TechnicalBacktestRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> TechnicalBacktestResponse:
    if not get_config().technical_backtest_enabled:
        raise HTTPException(status_code=503, detail="技术回测功能已禁用")
    try:
        service = TechnicalBacktestService()
        result = service.run_backtest(
            codes=request.codes,
            start_date=request.start_date,
            end_date=request.end_date,
            eval_window_days=request.eval_window_days,
        )
        return TechnicalBacktestResponse(**result)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": str(exc)},
        )
    except Exception as exc:
        logger.error(f"纯技术回测失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"纯技术回测失败: {str(exc)}"},
        )


@router.get(
    "/strategies",
    response_model=StrategyListResponse,
    responses={
        200: {"description": "策略列表"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取策略配置列表",
    description="获取所有可用的技术回测策略及其参数配置",
)
def get_strategies(
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    service: V2BacktestService = Depends(get_v2_backtest_service),
) -> StrategyListResponse:
    try:
        configs = service.list_strategies()
        return StrategyListResponse(
            strategies=[StrategyConfigItem(**dataclasses.asdict(c)) for c in configs]
        )
    except Exception as exc:
        logger.error(f"获取策略列表失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"获取策略列表失败: {str(exc)}"},
        )


@router.post(
    "/technical/batch",
    response_model=TechnicalBatchResponse,
    responses={
        200: {"description": "批量回测完成"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="批量参数组回测",
    description="为同一支股票运行多组策略参数的回测，返回每组参数的收益率曲线和交易明细",
)
def run_technical_batch(
    request: TechnicalBatchRequest,
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    service: V2BacktestService = Depends(get_v2_backtest_service),
) -> TechnicalBatchResponse:
    try:
        return service.run_batch(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": str(exc)},
        )
    except Exception as exc:
        logger.error(f"批量回测失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"批量回测失败: {str(exc)}"},
        )


def _get_template_repo(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> BacktestTemplateRepository:
    return BacktestTemplateRepository(db_manager)


def _get_session_repo(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> BacktestSessionRepository:
    return BacktestSessionRepository(db_manager)


@router.get(
    "/technical/templates",
    response_model=TemplateListResponse,
    responses={
        200: {"description": "模板列表"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取参数组模板列表",
    description="获取指定策略的已保存参数组模板",
)
def list_templates(
    strategy_id: str = Query(..., min_length=1, max_length=64),
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    repo: BacktestTemplateRepository = Depends(_get_template_repo),
) -> TemplateListResponse:
    try:
        templates = repo.list_by_strategy(strategy_id)
        return TemplateListResponse(
            templates=[TemplateItem(**t) for t in templates]
        )
    except Exception as exc:
        logger.error(f"获取模板列表失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "获取模板列表失败"},
        )


@router.post(
    "/technical/templates",
    response_model=TemplateItem,
    status_code=201,
    responses={
        201: {"description": "模板已保存"},
        422: {"description": "参数校验失败", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="保存参数组模板",
    description="保存当前参数组配置为模板",
)
def save_template(
    request: TemplateSaveRequest,
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    repo: BacktestTemplateRepository = Depends(_get_template_repo),
) -> TemplateItem:
    try:
        template = repo.save(request.strategy_id, request.name, request.params)
        return TemplateItem(**template)
    except Exception as exc:
        logger.error(f"保存模板失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "保存模板失败"},
        )


@router.delete(
    "/technical/templates/{template_id}",
    status_code=204,
    responses={
        204: {"description": "模板已删除"},
        404: {"description": "模板不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="删除参数组模板",
    description="删除指定的参数组模板",
)
def delete_template(
    template_id: int,
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    repo: BacktestTemplateRepository = Depends(_get_template_repo),
) -> None:
    try:
        deleted = repo.delete(template_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"模板不存在: id={template_id}"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"删除模板失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "删除模板失败"},
        )


# ============ P4: 自动持久化会话端点 ============

@router.get(
    "/technical/session",
    response_model=SessionItem,
    responses={
        200: {"description": "会话数据"},
        404: {"description": "未找到会话", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="加载回测会话",
    description="根据 stock_code 和 strategy_id 加载自动保存的回测会话",
)
def load_session(
    stock_code: str = Query(..., min_length=1, max_length=16),
    strategy_id: str = Query(..., min_length=1, max_length=64),
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    repo: BacktestSessionRepository = Depends(_get_session_repo),
) -> SessionItem:
    try:
        session = repo.get(stock_code, strategy_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "未找到回测会话"},
            )
        return SessionItem(**session)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"加载会话失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载会话失败"},
        )


@router.post(
    "/technical/session",
    response_model=SessionItem,
    status_code=200,
    responses={
        200: {"description": "会话已更新"},
        201: {"description": "会话已创建"},
        422: {"description": "参数校验失败", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="保存回测会话",
    description="自动保存/更新回测会话（按 stock_code + strategy_id upsert）",
)
def save_session(
    request: SessionSaveRequest,
    _tech_enabled: None = Depends(_require_technical_backtest_enabled),
    repo: BacktestSessionRepository = Depends(_get_session_repo),
) -> SessionItem:
    try:
        session = repo.upsert(
            request.stock_code,
            request.strategy_id,
            request.param_groups,
            request.batch_results,
        )
        return SessionItem(**session)
    except Exception as exc:
        logger.error(f"保存会话失败: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "保存会话失败"},
        )
