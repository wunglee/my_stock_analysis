"""RSI 策略

核心逻辑：
- 计算 Wilder's RSI 指标
- RSI 从超卖区（< oversold）回升 → buy
- RSI 从超买区（> overbought）回落 → sell

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


class RSIStrategy:
    """RSI 策略实现"""

    _CONFIG = StrategyConfig(
        id="rsi",
        name="RSI策略",
        description="基于 RSI 指标超买超卖产生买卖信号。RSI 从超卖区回升买入，从超买区回落卖出。",
        category="oscillator",
        parameters=[
            StrategyParameter(
                key="period",
                name="计算周期",
                type="number",
                default_value=14,
                min=2,
                max=60,
                step=1,
            ),
            StrategyParameter(
                key="overbought",
                name="超买阈值",
                type="number",
                default_value=70,
                min=50,
                max=90,
                step=1,
            ),
            StrategyParameter(
                key="oversold",
                name="超卖阈值",
                type="number",
                default_value=30,
                min=10,
                max=50,
                step=1,
            ),
        ],
        validation_rules=[
            ValidationRule(
                type="lessThan",
                param_a="oversold",
                param_b="overbought",
                message="超卖阈值必须小于超买阈值",
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
        # 第一个 RSI 值在索引 period，信号需要两根连续有效 RSI → period + 2
        return self._default("period") + 2

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

        oversold = params.get("oversold", self._default("oversold"))
        overbought = params.get("overbought", self._default("overbought"))

        if oversold >= overbought:
            errors.append("超卖阈值必须小于超买阈值")
        return errors

    def _calculate_rsi(self, closes: np.ndarray, period: int) -> np.ndarray:
        """计算 Wilder's RSI 序列

        Args:
            closes: 收盘价数组
            period: RSI 计算周期

        Returns:
            RSI 值数组（前 period 个值为 NaN）
        """
        n = len(closes)
        rsi = np.full(n, np.nan)

        if n < period + 1:
            return rsi

        delta = np.diff(closes)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)

        # 第一个 RSI 值基于 SMA（索引 period）
        avg_gain = np.mean(gain[:period])
        avg_loss = np.mean(loss[:period])

        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100.0 - (100.0 / (1.0 + rs))

        # Wilder's smoothing（从 period 开始递归计算后续值）
        for i in range(period, n - 1):
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period

            if avg_loss == 0:
                rsi[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: dict[str, Any],
    ) -> list[Signal]:
        if df.empty or len(df) < 2:
            return []

        period = int(params.get("period", self._default("period")))
        overbought = float(params.get("overbought", self._default("overbought")))
        oversold = float(params.get("oversold", self._default("oversold")))

        if len(df) < period + 1:
            return []

        closes = df["close"].values
        dates = df["date"].values if "date" in df.columns else df.index.astype(str)

        rsi = self._calculate_rsi(closes, period)

        signals = []
        for i in range(1, len(df)):
            prev_rsi = rsi[i - 1]
            curr_rsi = rsi[i]

            if np.isnan(prev_rsi) or np.isnan(curr_rsi):
                continue

            # 从超卖区回升 → buy：前一日 RSI <= oversold，当日 > oversold
            if prev_rsi <= oversold and curr_rsi > oversold:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="buy",
                        entry_price=float(closes[i]),
                        execution_price=None,
                        reasons=[f"RSI从超卖区回升 ({prev_rsi:.1f} → {curr_rsi:.1f})"],
                    )
                )
            # 从超买区回落 → sell：前一日 RSI >= overbought，当日 < overbought
            elif prev_rsi >= overbought and curr_rsi < overbought:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="sell",
                        entry_price=float(closes[i]),
                        execution_price=None,
                        reasons=[f"RSI从超买区回落 ({prev_rsi:.1f} → {curr_rsi:.1f})"],
                    )
                )

        return signals
