"""回测策略基础接口与数据结构

定义 ITechnicalStrategy Protocol、Signal dataclass 及策略配置相关数据结构。
所有 dataclass 均为 frozen（不可变），确保信号和配置在传递过程中不被意外修改。
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class Signal:
    """交易信号（不可变）

    V2 内部数据结构，不直接暴露给 API。
    信号在 date 日收盘时生成，由 EquityCalculator 在下一交易日开盘价执行。

    Attributes:
        date: 信号生成日期（YYYY-MM-DD）
        action: 信号动作 — buy / sell / wait
        entry_price: 参考价格（通常为收盘价），策略可选填
        execution_price: 参考执行价（策略可填收盘价作为参考，EquityCalculator 优先使用；
                        为 None 时由 EquityCalculator 查次日开盘价）
        reasons: 触发理由列表（如 ["短期均线上穿长期均线", "金叉形成"]）
    """

    date: str
    action: Literal["buy", "sell", "wait"]
    entry_price: Optional[float] = None
    execution_price: Optional[float] = None
    reasons: tuple[str, ...] = None

    def __post_init__(self):
        # frozen dataclass 需要通过 object.__setattr__ 设置默认值
        # 将 list 转换为 tuple 以支持哈希（dataclass 自动生成 __hash__）
        if self.reasons is None:
            object.__setattr__(self, "reasons", ())
        elif isinstance(self.reasons, list):
            object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class StrategyParameter:
    """策略参数定义

    **有意识取舍**：当前阶段仅支持 number / boolean 类型。首批 4 个策略
    （双均线、MACD、RSI、布林带）均只需数值参数，足够覆盖。
    后续可扩展为支持 enum / string 类型。
    """

    key: str  # 参数标识（英文，如 "short_period"）
    name: str  # 显示名（中文，如 "短期均线周期"）
    type: Literal["number", "boolean"]  # 参数类型
    default_value: int | float | bool  # 默认值
    min: Optional[int | float] = None  # 最小值（仅数值型）
    max: Optional[int | float] = None  # 最大值（仅数值型）
    step: Optional[int | float] = None  # 步长（前端滑动条用）


@dataclass(frozen=True)
class ValidationRule:
    """参数间校验规则

    **有意识取舍**：当前阶段仅支持 lessThan / greaterThan 两种基础规则，
    覆盖当前所有跨参数校验需求（如 short_period < long_period）。
    复杂交叉校验（如 A + B < C）可后续扩展。

    **V1/V2 命名差异**：V2 批量回测端点使用 camelCase（lessThan / greaterThan）。
    现有 V1 /technical 端点若使用 snake_case（less_than / greater_than），两者不冲突——
    V2 是新建端点，Schema 独立，不影响 V1 调用。
    """

    type: Literal["lessThan", "greaterThan"]
    param_a: str  # 参数 A（如 short_period）
    param_b: str  # 参数 B（如 long_period）
    message: str  # 校验失败提示（如 "短期周期必须小于长期周期"）


@dataclass(frozen=True)
class StrategyConfig:
    """策略配置（元数据）"""

    id: str  # 策略标识（如 "dual_ma"）
    name: str  # 显示名（如 "双均线策略"）
    description: str  # 策略描述（用于前端展示）
    category: Literal["trend", "oscillator", "volatility", "volume"]
    parameters: list[StrategyParameter]
    validation_rules: list[ValidationRule]


@runtime_checkable
class ITechnicalStrategy(Protocol):
    """技术指标策略接口

    所有可配置策略必须实现此 Protocol。通过结构化子类型检查，
    实现类无需显式继承。
    """

    @property
    def id(self) -> str:
        """策略唯一标识（如 "dual_ma"）"""
        ...

    @property
    def config(self) -> StrategyConfig:
        """策略配置元数据"""
        ...

    @property
    def min_warmup_bars(self) -> int:
        """最小预热数据条数（如均线策略需要 long_period 条数据才能计算）"""
        ...

    @property
    def required_columns(self) -> set[str]:
        """策略需要的 DataFrame 列名集合（如 {"close"} 或 {"close", "volume"}）"""
        ...

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """校验参数合法性，返回错误信息列表（空列表表示校验通过）

        Args:
            params: 参数组字典，key 为参数标识，value 为参数值

        Returns:
            错误信息列表，空列表表示校验通过
        """
        ...

    def generate_signals(
        self,
        df: pd.DataFrame,
        params: dict[str, Any],
    ) -> list[Signal]:
        """基于 K 线数据和参数生成信号列表

        Args:
            df: 标准 OHLCV DataFrame，列包含 required_columns 中定义的列
            params: 参数组字典

        Returns:
            信号列表，按日期升序排列。wait 信号可包含在列表中（用于调试），
            也可仅包含 buy / sell 信号。EquityCalculator 只处理 buy / sell。
        """
        ...
