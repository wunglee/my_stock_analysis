# -*- coding: utf-8 -*-
"""Backtest API schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class BacktestRunRequest(BaseModel):
    code: Optional[str] = Field(None, description="仅回测指定股票")
    force: bool = Field(False, description="强制重新计算")
    eval_window_days: Optional[int] = Field(None, ge=1, le=120, description="评估窗口（交易日数）")
    min_age_days: Optional[int] = Field(None, ge=0, le=365, description="分析记录最小天龄（0=不限）")
    limit: int = Field(200, ge=1, le=2000, description="最多处理的分析记录数")


class BacktestRunResponse(BaseModel):
    processed: int = Field(..., description="候选记录数")
    saved: int = Field(..., description="写入回测结果数")
    completed: int = Field(..., description="完成回测数")
    insufficient: int = Field(..., description="数据不足数")
    errors: int = Field(..., description="错误数")


class BacktestResultItem(BaseModel):
    analysis_history_id: int
    code: str
    stock_name: Optional[str] = None
    analysis_date: Optional[str] = None
    eval_window_days: int
    engine_version: str
    eval_status: str
    evaluated_at: Optional[str] = None
    operation_advice: Optional[str] = None
    trend_prediction: Optional[str] = None
    position_recommendation: Optional[str] = None
    start_price: Optional[float] = None
    end_close: Optional[float] = None
    max_high: Optional[float] = None
    min_low: Optional[float] = None
    stock_return_pct: Optional[float] = None
    actual_return_pct: Optional[float] = None
    actual_movement: Optional[str] = None
    direction_expected: Optional[str] = None
    direction_correct: Optional[bool] = None
    outcome: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    hit_stop_loss: Optional[bool] = None
    hit_take_profit: Optional[bool] = None
    first_hit: Optional[str] = None
    first_hit_date: Optional[str] = None
    first_hit_trading_days: Optional[int] = None
    simulated_entry_price: Optional[float] = None
    simulated_exit_price: Optional[float] = None
    simulated_exit_reason: Optional[str] = None
    simulated_return_pct: Optional[float] = None


class BacktestResultsResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[BacktestResultItem] = Field(default_factory=list)


class PerformanceMetrics(BaseModel):
    scope: str
    code: Optional[str] = None
    eval_window_days: int
    engine_version: str
    computed_at: Optional[str] = None

    total_evaluations: int
    completed_count: int
    insufficient_count: int
    long_count: int
    cash_count: int
    win_count: int
    loss_count: int
    neutral_count: int

    direction_accuracy_pct: Optional[float] = None
    win_rate_pct: Optional[float] = None
    neutral_rate_pct: Optional[float] = None
    avg_stock_return_pct: Optional[float] = None
    avg_simulated_return_pct: Optional[float] = None

    stop_loss_trigger_rate: Optional[float] = None
    take_profit_trigger_rate: Optional[float] = None
    ambiguous_rate: Optional[float] = None
    avg_days_to_first_hit: Optional[float] = None

    advice_breakdown: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


# ============ 纯技术回测 Schema ============

class TechnicalBacktestRequest(BaseModel):
    codes: List[str] = Field(..., min_length=1, max_length=10, description="股票代码列表")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    eval_window_days: int = Field(10, ge=1, le=120, description="评估窗口天数")


class KlineDataItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class TechnicalRuleItem(BaseModel):
    name: str
    condition: str
    sample_count: int
    win_rate: float
    avg_return_5d: float
    confidence: float


class TechnicalSignalItem(BaseModel):
    date: str
    action: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    confidence: float


class TechnicalEvaluationItem(BaseModel):
    signal_date: str
    action: str
    outcome: str
    stock_return_pct: float
    hit_take_profit: bool
    hit_stop_loss: bool
    direction_correct: bool


class TechnicalStockResult(BaseModel):
    code: str
    stock_name: str
    date_range: str
    total_signals: int
    win_rate: float
    avg_return: float
    max_drawdown: float
    kline_data: List[KlineDataItem] = Field(default_factory=list)
    rules: List[TechnicalRuleItem] = Field(default_factory=list)
    signals: List[TechnicalSignalItem] = Field(default_factory=list)
    evaluations: List[TechnicalEvaluationItem] = Field(default_factory=list)


class TechnicalCorrelationItem(BaseModel):
    code_a: str
    code_b: str
    price_correlation: float


class TechnicalBacktestResponse(BaseModel):
    meta: Dict[str, Any]
    per_stock: Dict[str, TechnicalStockResult]
    cross_stock: Dict[str, List[TechnicalCorrelationItem]]


# ============ v2.0: 策略配置 + 批量参数组回测 Schema ============

class StrategyParameterItem(BaseModel):
    key: str
    name: str
    type: Literal["number", "boolean"]
    default_value: Union[int, float, bool]
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None


class ValidationRuleItem(BaseModel):
    type: Literal["lessThan", "greaterThan"]
    param_a: str
    param_b: str
    message: str


class StrategyConfigItem(BaseModel):
    id: str
    name: str
    description: str
    category: str  # "trend" | "oscillator" | "volatility" | "volume"
    parameters: List[StrategyParameterItem] = Field(default_factory=list)
    validation_rules: List[ValidationRuleItem] = Field(default_factory=list)


class ParamGroupRequest(BaseModel):
    id: str
    name: str
    params: Dict[str, Union[int, float, bool]]


class TechnicalBatchRequest(BaseModel):
    codes: List[str] = Field(..., min_length=1, max_length=1)
    start_date: str
    end_date: str
    eval_window_days: int = Field(10, ge=1, le=120)
    strategy_id: str
    param_groups: List[ParamGroupRequest] = Field(..., min_length=1, max_length=6)


class EquityCurvePointItem(BaseModel):
    date: str
    strategy_value: float
    benchmark_value: float


class TradeRecordItem(BaseModel):
    id: int
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float
    pnl_amount: float
    hold_days: int
    reason: str


class ParamGroupResultItem(BaseModel):
    group: ParamGroupRequest
    status: Literal["success", "insufficient_data", "error"] = "success"
    error_message: Optional[str] = Field(None, description="错误详情，status 非 success 时填充")
    stock_result: Optional[TechnicalStockResult] = None
    equity_curve: List[EquityCurvePointItem] = Field(default_factory=list)
    trades: List[TradeRecordItem] = Field(default_factory=list)


class StrategyListResponse(BaseModel):
    strategies: List[StrategyConfigItem] = Field(default_factory=list)


class BatchMeta(BaseModel):
    """批量回测批次元数据"""
    mode: str = "technical_batch"
    codes: List[str] = Field(default_factory=list)
    date_range: str = ""
    eval_window_days: int = 0
    strategy_id: str
    generated_at: str = ""
    error: Optional[str] = None


class TechnicalBatchResponse(BaseModel):
    meta: BatchMeta
    results: List[ParamGroupResultItem] = Field(default_factory=list)


# ============ P3: 参数组模板 Schema ============

class TemplateSaveRequest(BaseModel):
    strategy_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    params: List[Dict] = Field(..., min_length=1, max_length=6)


class TemplateItem(BaseModel):
    id: int
    strategy_id: str
    name: str
    params: List[Dict]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TemplateListResponse(BaseModel):
    templates: List[TemplateItem] = Field(default_factory=list)


# ============ P4: 自动持久化会话 Schema ============

class SessionSaveRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=16)
    strategy_id: str = Field(..., min_length=1, max_length=64)
    param_groups: List[Dict] = Field(..., min_length=1, max_length=6)
    batch_results: Optional[List[Dict]] = None


class SessionItem(BaseModel):
    id: int
    stock_code: str
    strategy_id: str
    param_groups: List[Dict]
    batch_results: Optional[List[Dict]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
