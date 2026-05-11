"""测试 TechnicalBacktestService"""

import pandas as pd
import pytest

from api.v1.schemas.backtest import (
    ParamGroupRequest,
    TechnicalBatchRequest,
)
from src.services.backtest.engine.data_adapter import IDataFetcher
from src.services.backtest.engine.equity_calculator import TradingCalendar
from src.services.backtest.service import TechnicalBacktestService
from src.services.backtest.strategies.registry import StrategyRegistry


class SimpleCalendar:
    """测试用交易日历：每天均为交易日，下一日 = 日期+1"""

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        return date + pd.Timedelta(days=1)

    def is_trading_day(self, date: pd.Timestamp) -> bool:
        return True


class MockDataFetcher:
    """模拟数据获取器"""

    def __init__(self, df: pd.DataFrame | None):
        self._df = df

    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        return self._df


class TestTechnicalBacktestService:
    """批量回测服务测试"""

    def _make_df(self, prices: list[float], dates: list[str] | None = None) -> pd.DataFrame:
        if dates is None:
            dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
        return pd.DataFrame({
            "date": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000] * len(prices),
        })

    def _make_service(self, df: pd.DataFrame | None) -> TechnicalBacktestService:
        registry = StrategyRegistry()
        from src.services.backtest.strategies.dual_ma import DualMAStrategy
        registry.register(DualMAStrategy())
        fetcher = MockDataFetcher(df)
        return TechnicalBacktestService(registry, fetcher, SimpleCalendar())

    def test_single_param_group(self):
        """单参数组完整回测流程"""
        prices = [100.0] * 50
        df = self._make_df(prices)
        service = self._make_service(df)

        request = TechnicalBatchRequest(
            codes=["000001"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="dual_ma",
            param_groups=[
                ParamGroupRequest(id="g1", name="默认参数", params={"short_period": 5, "long_period": 20})
            ],
        )

        result = service.run_batch(request)

        assert len(result.results) == 1
        group_result = result.results[0]
        assert group_result.status == "success"
        assert group_result.group.id == "g1"
        # 权益曲线应有数据
        assert len(group_result.equity_curve) > 0
        # 无信号时应无交易
        assert group_result.trades == []

    def test_multiple_param_groups(self):
        """多参数组批量回测"""
        prices = [100.0] * 50
        df = self._make_df(prices)
        service = self._make_service(df)

        request = TechnicalBatchRequest(
            codes=["000001"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="dual_ma",
            param_groups=[
                ParamGroupRequest(id="g1", name="保守", params={"short_period": 10, "long_period": 30}),
                ParamGroupRequest(id="g2", name="激进", params={"short_period": 5, "long_period": 10}),
                ParamGroupRequest(id="g3", name="默认", params={"short_period": 5, "long_period": 20}),
            ],
        )

        result = service.run_batch(request)

        assert len(result.results) == 3
        assert result.results[0].group.id == "g1"
        assert result.results[1].group.id == "g2"
        assert result.results[2].group.id == "g3"
        # 所有组都成功（无交叉的均线不产生信号）
        assert all(r.status == "success" for r in result.results)

    def test_strategy_not_found(self):
        """策略不存在时应返回 error，且不应调用数据获取"""
        class TrackingFetcher:
            """追踪是否被调用的模拟获取器"""
            def __init__(self):
                self.called = False
            def get_daily_data(self, symbol: str, start_date: str, end_date: str):
                self.called = True
                return None

        registry = StrategyRegistry()
        fetcher = TrackingFetcher()
        service = TechnicalBacktestService(registry, fetcher, SimpleCalendar())

        request = TechnicalBatchRequest(
            codes=["000001"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="nonexistent",
            param_groups=[
                ParamGroupRequest(id="g1", name="测试", params={})
            ],
        )

        result = service.run_batch(request)

        assert len(result.results) == 1
        assert result.results[0].status == "error"
        assert "策略未找到" in result.results[0].error_message
        assert not fetcher.called, "策略不存在时不应调用数据获取器"

    def test_no_data_returns_error(self):
        """无数据时返回 error"""
        service = self._make_service(None)

        request = TechnicalBatchRequest(
            codes=["000001"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="dual_ma",
            param_groups=[
                ParamGroupRequest(id="g1", name="测试", params={"short_period": 5, "long_period": 20})
            ],
        )

        result = service.run_batch(request)

        assert len(result.results) == 1
        assert result.results[0].status == "error"
        assert result.results[0].error_message == "无数据"

    def test_param_validation_error(self):
        """参数校验失败应返回 error"""
        prices = [100.0] * 50
        df = self._make_df(prices)
        service = self._make_service(df)

        request = TechnicalBatchRequest(
            codes=["000001"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="dual_ma",
            param_groups=[
                ParamGroupRequest(id="g1", name="错误参数", params={"short_period": 30, "long_period": 5})
            ],
        )

        result = service.run_batch(request)

        assert len(result.results) == 1
        assert result.results[0].status == "error"
        assert result.results[0].error_message is not None
        assert "短期周期" in result.results[0].error_message

    def test_isolation_one_group_error(self):
        """异常隔离：1 组参数异常，其他组正常"""
        prices = [100.0] * 50
        df = self._make_df(prices)
        service = self._make_service(df)

        request = TechnicalBatchRequest(
            codes=["000001"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="dual_ma",
            param_groups=[
                ParamGroupRequest(id="g1", name="正常", params={"short_period": 5, "long_period": 20}),
                ParamGroupRequest(id="g2", name="错误", params={"short_period": 30, "long_period": 5}),
                ParamGroupRequest(id="g3", name="正常2", params={"short_period": 10, "long_period": 30}),
            ],
        )

        result = service.run_batch(request)

        assert len(result.results) == 3
        assert result.results[0].status == "success"
        assert result.results[1].status == "error"
        assert result.results[1].error_message is not None
        assert result.results[2].status == "success"

    def test_multiple_codes_raises(self):
        """多股票请求应抛出 ValueError"""
        prices = [100.0] * 50
        df = self._make_df(prices)
        service = self._make_service(df)

        # 用 model_construct 绕过 pydantic max_length=1 校验，测试 service 层防御
        request = TechnicalBatchRequest.model_construct(
            codes=["000001", "000002"],
            start_date="2024-01-01",
            end_date="2024-02-19",
            strategy_id="dual_ma",
            param_groups=[
                ParamGroupRequest(id="g1", name="测试", params={"short_period": 5, "long_period": 20})
            ],
        )

        with pytest.raises(ValueError, match="当前仅支持单股票回测"):
            service.run_batch(request)
