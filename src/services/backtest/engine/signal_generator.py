"""信号生成器

职责：代理调用策略生成信号，附加预热数据检查。
不直接暴露给外部，由 TechnicalBacktestService 内部创建和使用。
"""

from typing import Any

import pandas as pd

from src.services.backtest.exceptions import InsufficientDataError
from src.services.backtest.strategies.base import ITechnicalStrategy, Signal


class SignalGenerator:
    """信号生成器

    执行流程：
    1. 校验 df 列是否包含 strategy.required_columns
    2. 校验 df 长度 >= strategy.min_warmup_bars
    3. 调用 strategy.generate_signals(df, params)
    4. 返回信号列表（不做过滤或修改）
    """

    def generate(
        self,
        strategy: ITechnicalStrategy,
        df: pd.DataFrame,
        params: dict[str, Any],
    ) -> list[Signal]:
        """生成信号

        Args:
            strategy: 策略实例
            df: 标准 OHLCV DataFrame
            params: 参数组字典

        Returns:
            信号列表，按日期升序排列

        Raises:
            InsufficientDataError: 数据列缺失或数据条数不足
        """
        # 1. 校验列
        missing_cols = strategy.required_columns - set(df.columns)
        if missing_cols:
            raise InsufficientDataError(
                f"数据缺少必需列: {missing_cols}"
            )

        # 2. 校验长度
        if len(df) < strategy.min_warmup_bars:
            raise InsufficientDataError(
                f"数据条数不足: 需要 {strategy.min_warmup_bars} 条，实际 {len(df)} 条"
            )

        # 3. 生成信号
        signals = strategy.generate_signals(df, params)

        # 4. 按日期升序排序
        signals.sort(key=lambda s: s.date)

        return signals
