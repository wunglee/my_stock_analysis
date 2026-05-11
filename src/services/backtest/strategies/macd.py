"""MACD 策略

核心逻辑：
- 计算 DIF（快慢 EMA 差）和 DEA（DIF 的 EMA）
- DIF 上穿 DEA（金叉）→ buy
- DIF 下穿 DEA（死叉）→ sell
- 无交叉 → wait

信号执行语义：收盘生成信号，次日开盘执行（由 EquityCalculator 处理）。
"""

from typing import Any

import pandas as pd
import numpy as np

from src.services.backtest.strategies.base import (
    Signal,
    StrategyConfig,
    StrategyParameter,
    ValidationRule,
)


class MACDStrategy:
    """MACD 策略实现"""

    _CONFIG = StrategyConfig(
        id="macd",
        name="MACD策略",
        description="基于 MACD 指标的金叉死叉产生买卖信号。DIF 上穿 DEA 买入，DIF 下穿 DEA 卖出。",
        category="trend",
        parameters=[
            StrategyParameter(
                key="fast",
                name="快线周期",
                type="number",
                default_value=12,
                min=2,
                max=60,
                step=1,
            ),
            StrategyParameter(
                key="slow",
                name="慢线周期",
                type="number",
                default_value=26,
                min=5,
                max=120,
                step=1,
            ),
            StrategyParameter(
                key="signal",
                name="信号线周期",
                type="number",
                default_value=9,
                min=2,
                max=60,
                step=1,
            ),
        ],
        validation_rules=[
            ValidationRule(
                type="lessThan",
                param_a="fast",
                param_b="slow",
                message="快线周期必须小于慢线周期",
            ),
        ],
    )

    @property
    def id(self) -> str:
        return self._CONFIG.id

    @property
    def config(self) -> StrategyConfig:
        return self._CONFIG

    @property
    def min_warmup_bars(self) -> int:
        return self._default("slow") + self._default("signal")

    @property
    def required_columns(self) -> set[str]:
        return {"close"}

    def _default(self, key: str) -> int | float:
        for p in self._CONFIG.parameters:
            if p.key == key:
                return p.default_value
        raise KeyError(f"Unknown parameter: {key}")

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []

        for p in self._CONFIG.parameters:
            if p.key in params and p.type == "number":
                val = params[p.key]
                if p.min is not None and val < p.min:
                    errors.append(f"{p.name}不能小于{p.min}")
                if p.max is not None and val > p.max:
                    errors.append(f"{p.name}不能大于{p.max}")

        fast = params.get("fast", self._default("fast"))
        slow = params.get("slow", self._default("slow"))

        if fast >= slow:
            errors.append("快线周期必须小于慢线周期")
        return errors

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: dict[str, Any],
    ) -> list[Signal]:
        if df.empty or len(df) < 2:
            return []

        fast_period = int(params.get("fast", self._default("fast")))
        slow_period = int(params.get("slow", self._default("slow")))
        signal_period = int(params.get("signal", self._default("signal")))

        min_required = slow_period + signal_period
        if len(df) < min_required:
            return []

        closes = df["close"].values
        dates = df["date"].values if "date" in df.columns else df.index.astype(str)

        # 计算 EMA
        fast_ema = pd.Series(closes).ewm(span=fast_period, adjust=False).mean().values
        slow_ema = pd.Series(closes).ewm(span=slow_period, adjust=False).mean().values

        # DIF = fast_ema - slow_ema
        dif = fast_ema - slow_ema

        # DEA = EMA of DIF
        dea = pd.Series(dif).ewm(span=signal_period, adjust=False).mean().values

        signals = []
        for i in range(1, len(df)):
            prev_dif = dif[i - 1]
            prev_dea = dea[i - 1]
            curr_dif = dif[i]
            curr_dea = dea[i]

            if np.isnan(prev_dif) or np.isnan(prev_dea) or np.isnan(curr_dif) or np.isnan(curr_dea):
                continue

            # 金叉：前一日 DIF <= DEA，当日 DIF > DEA
            if prev_dif <= prev_dea and curr_dif > curr_dea:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="buy",
                        entry_price=float(closes[i]),
                        execution_price=None,
                        reasons=[f"金叉：DIF({curr_dif:.4f})上穿DEA({curr_dea:.4f})"],
                    )
                )
            # 死叉：前一日 DIF >= DEA，当日 DIF < DEA
            elif prev_dif >= prev_dea and curr_dif < curr_dea:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="sell",
                        entry_price=float(closes[i]),
                        execution_price=None,
                        reasons=[f"死叉：DIF({curr_dif:.4f})下穿DEA({curr_dea:.4f})"],
                    )
                )

        return signals
