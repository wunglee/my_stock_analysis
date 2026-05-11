"""批量回测服务

串联信号生成和权益计算，提供批量参数组回测入口。
"""

from datetime import datetime, timezone

from api.v1.schemas.backtest import (
    BatchMeta,
    EquityCurvePointItem,
    KlineDataItem,
    ParamGroupRequest,
    ParamGroupResultItem,
    TechnicalBatchRequest,
    TechnicalBatchResponse,
    TechnicalStockResult,
    TradeRecordItem,
)
from src.services.backtest.engine.data_adapter import IDataFetcher
from src.services.backtest.engine.equity_calculator import EquityCalculator, TradingCalendar
from src.services.backtest.engine.signal_generator import SignalGenerator
from src.services.backtest.exceptions import InsufficientDataError
from src.services.backtest.strategies.base import Signal
from src.services.backtest.strategies.registry import StrategyRegistry


class TechnicalBacktestService:
    """纯技术回测批量服务

    职责：
    1. 获取策略和数据
    2. 对每组参数串行执行回测
    3. 异常隔离：单组失败不影响其他组
    4. 组装结果返回
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        data_fetcher: IDataFetcher,
        calendar: TradingCalendar,
    ):
        self._registry = registry
        self._data_fetcher = data_fetcher
        self._signal_generator = SignalGenerator()
        self._equity_calculator = EquityCalculator(calendar=calendar)

    def list_strategies(self) -> list:
        """列出所有已注册策略的配置"""
        return self._registry.list_all()

    def run_batch(self, request: TechnicalBatchRequest) -> TechnicalBatchResponse:
        """执行批量回测"""
        if len(request.codes) != 1:
            raise ValueError(f"当前仅支持单股票回测，收到 {len(request.codes)} 个")
        code = request.codes[0]

        # 先校验策略（纯内存，成本低）
        try:
            strategy = self._registry.get(request.strategy_id)
        except KeyError:
            results = [
                self._build_error_result(group, f"策略未找到: {request.strategy_id}")
                for group in request.param_groups
            ]
            return TechnicalBatchResponse(
                meta=BatchMeta(
                    mode="technical_batch",
                    codes=request.codes,
                    date_range=f"{request.start_date}~{request.end_date}",
                    eval_window_days=request.eval_window_days,
                    strategy_id=request.strategy_id,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    error=f"策略未找到: {request.strategy_id}",
                ),
                results=results,
            )

        # 再获取数据
        df = self._data_fetcher.get_daily_data(code, request.start_date, request.end_date)
        if df is None or df.empty:
            results = [
                self._build_error_result(group, "无数据")
                for group in request.param_groups
            ]
            return TechnicalBatchResponse(
                meta=BatchMeta(
                    mode="technical_batch",
                    codes=request.codes,
                    date_range=f"{request.start_date}~{request.end_date}",
                    eval_window_days=request.eval_window_days,
                    strategy_id=request.strategy_id,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    error="无数据",
                ),
                results=results,
            )

        # 对每组参数执行回测
        results = []
        for group in request.param_groups:
            result = self._run_single_group(strategy, df, code, group)
            results.append(result)

        meta = BatchMeta(
            mode="technical_batch",
            codes=request.codes,
            date_range=f"{request.start_date}~{request.end_date}",
            eval_window_days=request.eval_window_days,
            strategy_id=request.strategy_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return TechnicalBatchResponse(meta=meta, results=results)

    def _run_single_group(
        self,
        strategy,
        df,
        code: str,
        group: ParamGroupRequest,
    ) -> ParamGroupResultItem:
        """执行单组参数回测"""
        # 参数校验
        errors = strategy.validate_params(group.params)
        if errors:
            return self._build_error_result(group, "; ".join(errors))

        try:
            # 生成信号
            signals = self._signal_generator.generate(strategy, df, group.params)

            # 计算权益
            equity_result = self._equity_calculator.calculate(df, signals)

            # 组装结果
            return self._build_success_result(group, df, signals, equity_result, code)

        except InsufficientDataError as e:
            return self._build_insufficient_data_result(group, str(e))
        except Exception as e:
            return self._build_error_result(group, str(e))

    def _build_success_result(
        self,
        group: ParamGroupRequest,
        df,
        signals: list[Signal],
        equity_result,
        code: str,
    ) -> ParamGroupResultItem:
        """构建成功结果"""
        # 转换权益曲线
        equity_curve = [
            EquityCurvePointItem(
                date=pt.date,
                strategy_value=pt.strategy_value,
                benchmark_value=pt.benchmark_value,
            )
            for pt in equity_result.equity_curve
        ]

        # 转换交易记录
        trades = [
            TradeRecordItem(
                id=t.id,
                entry_date=t.entry_date,
                entry_price=t.entry_price,
                exit_date=t.exit_date,
                exit_price=t.exit_price,
                return_pct=t.return_pct,
                pnl_amount=t.pnl_amount,
                hold_days=t.hold_days,
                reason=t.reason,
            )
            for t in equity_result.trades
        ]

        # 构建 stock_result
        kline_data = [
            KlineDataItem(
                date=str(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
            for _, row in df.iterrows()
        ]

        stock_result = TechnicalStockResult(
            code=code,
            stock_name=code,
            date_range=f"{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}",
            total_signals=len([s for s in signals if s.action in ("buy", "sell")]),
            win_rate=equity_result.win_rate,
            avg_return=equity_result.total_return,
            max_drawdown=equity_result.max_drawdown,
            kline_data=kline_data,
            rules=[],
            signals=[],
            evaluations=[],
        )

        return ParamGroupResultItem(
            group=group,
            status="success",
            stock_result=stock_result,
            equity_curve=equity_curve,
            trades=trades,
        )

    def _build_error_result(
        self, group: ParamGroupRequest, message: str
    ) -> ParamGroupResultItem:
        """构建错误结果"""
        return ParamGroupResultItem(
            group=group,
            status="error",
            error_message=message,
            equity_curve=[],
            trades=[],
        )

    def _build_insufficient_data_result(
        self, group: ParamGroupRequest, message: str
    ) -> ParamGroupResultItem:
        """构建数据不足结果"""
        return ParamGroupResultItem(
            group=group,
            status="insufficient_data",
            error_message=message,
            equity_curve=[],
            trades=[],
        )
