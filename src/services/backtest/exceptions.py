"""回测引擎异常类"""


class StrategyNotFoundError(ValueError):
    """策略不存在"""
    pass


class InsufficientDataError(ValueError):
    """K线数据不足"""
    pass


class ParamValidationError(ValueError):
    """参数校验失败"""

    def __init__(self, group_id: str, errors: list[dict]):
        self.group_id = group_id
        self.errors = errors
        super().__init__(f"参数组 {group_id} 校验失败: {errors}")
