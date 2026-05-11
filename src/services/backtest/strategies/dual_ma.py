"""双均线策略（Dual Moving Average）

核心逻辑：
- 短期均线上穿长期均线（金叉）→ buy
- 短期均线下穿长期均线（死叉）→ sell
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


class DualMAStrategy:
    """双均线策略实现"""

    _CONFIG = StrategyConfig(
        id="dual_ma",
        name="双均线策略",
        description="基于短期和长期均线交叉产生买卖信号。短期均线上穿长期均线买入，下穿卖出。",
        category="trend",
        parameters=[
            StrategyParameter(
                key="short_period",
                name="短期均线周期",
                type="number",
                default_value=5,
                min=2,
                max=60,
                step=1,
            ),
            StrategyParameter(
                key="long_period",
                name="长期均线周期",
                type="number",
                default_value=20,
                min=5,
                max=250,
                step=1,
            ),
        ],
        validation_rules=[
            ValidationRule(
                type="lessThan",
                param_a="short_period",
                param_b="long_period",
                message="短期周期必须小于长期周期",
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
        return self._default("long_period")

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

        # 参数范围校验
        for p in self._CONFIG.parameters:
            if p.key in params and p.type == "number":
                val = params[p.key]
                if p.min is not None and val < p.min:
                    errors.append(f"{p.name}不能小于{p.min}")
                if p.max is not None and val > p.max:
                    errors.append(f"{p.name}不能大于{p.max}")

        short = params.get("short_period", self._default("short_period"))
        long = params.get("long_period", self._default("long_period"))

        if short >= long:
            errors.append("短期周期必须小于长期周期")
        return errors

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: dict[str, Any],
    ) -> list[Signal]:
        if df.empty or len(df) < 2:
            return []

        short_period = int(params.get("short_period", self._default("short_period")))
        long_period = int(params.get("long_period", self._default("long_period")))

        # 数据不足时无法计算均线
        if len(df) < long_period:
            return []

        closes = df["close"].values
        dates = df["date"].values if "date" in df.columns else df.index.astype(str)

        # 计算均线
        short_ma = pd.Series(closes).rolling(window=short_period, min_periods=short_period).mean().values
        long_ma = pd.Series(closes).rolling(window=long_period, min_periods=long_period).mean().values

        signals = []
        for i in range(1, len(df)):
            prev_short = short_ma[i - 1]
            prev_long = long_ma[i - 1]
            curr_short = short_ma[i]
            curr_long = long_ma[i]

            # 跳过 NaN（预热期）
            if np.isnan(prev_short) or np.isnan(prev_long) or np.isnan(curr_short) or np.isnan(curr_long):
                continue

            # 金叉：前一日短期 <= 长期，当日短期 > 长期
            if prev_short <= prev_long and curr_short > curr_long:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="buy",
                        entry_price=float(closes[i]),
                        execution_price=None,  # EquityCalculator 负责查次日开盘价
                        reasons=[f"金叉：短期均线({short_period}日)上穿长期均线({long_period}日)"],
                    )
                )
            # 死叉：前一日短期 >= 长期，当日短期 < 长期
            elif prev_short >= prev_long and curr_short < curr_long:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="sell",
                        entry_price=float(closes[i]),
                        execution_price=None,
                        reasons=[f"死叉：短期均线({short_period}日)下穿长期均线({long_period}日)"],
                    )
                )

        return signals
