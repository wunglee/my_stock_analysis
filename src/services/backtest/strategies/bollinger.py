"""布林带策略

核心逻辑：
- 计算中轨（SMA）、上轨（中轨 + k×σ）、下轨（中轨 - k×σ）
- 收盘价下穿上轨（从上方向下穿）→ sell（价格回归中轨）
- 收盘价上穿下轨（从下方向上穿）→ buy（价格回归中轨）

信号执行语义：收盘生成信号，次日开盘执行（由 EquityCalculator 处理）。
"""

from typing import Any

import pandas as pd
import numpy as np

from src.services.backtest.strategies.base import (
    Signal,
    StrategyConfig,
    StrategyParameter,
)


class BollingerStrategy:
    """布林带策略实现"""

    _CONFIG = StrategyConfig(
        id="bollinger",
        name="布林带策略",
        description="基于布林带指标产生买卖信号。价格触及下轨反弹买入，触及上轨回落卖出。",
        category="volatility",
        parameters=[
            StrategyParameter(
                key="period",
                name="计算周期",
                type="number",
                default_value=20,
                min=5,
                max=120,
                step=1,
            ),
            StrategyParameter(
                key="std_dev",
                name="标准差倍数",
                type="number",
                default_value=2.0,
                min=1.0,
                max=4.0,
                step=0.1,
            ),
        ],
        validation_rules=[],  # 无跨参数校验规则
    )

    @property
    def id(self) -> str:
        return self._CONFIG.id

    @property
    def config(self) -> StrategyConfig:
        return self._CONFIG

    @property
    def min_warmup_bars(self) -> int:
        return self._default("period")

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
        return errors

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: dict[str, Any],
    ) -> list[Signal]:
        if df.empty or len(df) < 2:
            return []

        period = int(params.get("period", self._default("period")))
        std_dev = float(params.get("std_dev", self._default("std_dev")))

        if len(df) < period:
            return []

        closes = df["close"].values
        dates = df["date"].values if "date" in df.columns else df.index.astype(str)

        # 中轨（SMA）、标准差
        middle = pd.Series(closes).rolling(window=period, min_periods=period).mean().values
        std = pd.Series(closes).rolling(window=period, min_periods=period).std(ddof=0).values

        # 上轨 = 中轨 + k×σ，下轨 = 中轨 - k×σ
        upper = middle + std_dev * std
        lower = middle - std_dev * std

        signals = []
        for i in range(1, len(df)):
            curr_mid = middle[i]
            prev_close = closes[i - 1]
            curr_close = closes[i]
            prev_upper = upper[i - 1]
            curr_upper = upper[i]
            prev_lower = lower[i - 1]
            curr_lower = lower[i]

            # 跳过 NaN（预热期）
            if np.isnan(curr_mid) or np.isnan(curr_upper) or np.isnan(curr_lower):
                continue
            if np.isnan(prev_upper) or np.isnan(prev_lower):
                continue

            # 上穿上轨（价格从下方向上穿到上轨之上）→ sell
            # 前一日收盘 <= 前一日上轨，当日收盘 > 当日上轨
            if prev_close <= prev_upper and curr_close > curr_upper:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="sell",
                        entry_price=float(curr_close),
                        execution_price=None,
                        reasons=[f"价格触及上轨 (收盘{curr_close:.2f} > 上轨{curr_upper:.2f})"],
                    )
                )
            # 下穿下轨（价格从上方向下穿到下轨之下）→ buy
            # 前一日收盘 >= 前一日下轨，当日收盘 < 当日下轨
            elif prev_close >= prev_lower and curr_close < curr_lower:
                signals.append(
                    Signal(
                        date=str(dates[i]),
                        action="buy",
                        entry_price=float(curr_close),
                        execution_price=None,
                        reasons=[f"价格触及下轨 (收盘{curr_close:.2f} < 下轨{curr_lower:.2f})"],
                    )
                )

        return signals
