# -*- coding: utf-8 -*-
"""V2 批量回测 API 测试"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fastapi import HTTPException

from api.app import create_app
from api.v1.endpoints.technical_backtest import (
    _require_technical_backtest_enabled,
    get_v2_backtest_service,
)
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

    def __init__(self, df=None):
        self._df = df

    def get_daily_data(self, symbol: str, start_date: str, end_date: str):
        return self._df


def _make_df(prices: list[float], dates: list[str] | None = None) -> pd.DataFrame:
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


def _make_service(df=None) -> TechnicalBacktestService:
    registry = StrategyRegistry()
    from src.services.backtest.strategies.dual_ma import DualMAStrategy
    registry.register(DualMAStrategy())
    fetcher = MockDataFetcher(df)
    return TechnicalBacktestService(registry, fetcher, SimpleCalendar())


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestGetStrategiesV2:
    """GET /strategies V2 端点测试"""

    def test_returns_strategy_list(self, client):
        """返回非空策略列表，包含 dual_ma"""
        client.app.dependency_overrides[get_v2_backtest_service] = _make_service
        try:
            response = client.get("/api/v1/backtest/strategies")

            assert response.status_code == 200
            data = response.json()
            assert "strategies" in data
            assert len(data["strategies"]) >= 1
            ids = [s["id"] for s in data["strategies"]]
            assert "dual_ma" in ids
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)


class TestBatchBacktestV2:
    """POST /technical/batch V2 端点测试"""

    def _batch_request(self, strategy_id="dual_ma", param_groups=None):
        if param_groups is None:
            param_groups = [
                {"id": "g1", "name": "默认", "params": {"short_period": 5, "long_period": 20}}
            ]
        return {
            "codes": ["000001"],
            "start_date": "2024-01-01",
            "end_date": "2024-02-19",
            "eval_window_days": 10,
            "strategy_id": strategy_id,
            "param_groups": param_groups,
        }

    def test_success_single_group(self, client):
        """单参数组正常回测返回 200 + success"""
        prices = [100.0] * 50
        df = _make_df(prices)

        client.app.dependency_overrides[get_v2_backtest_service] = lambda: _make_service(df)
        try:
            response = client.post("/api/v1/backtest/technical/batch", json=self._batch_request())

            assert response.status_code == 200
            data = response.json()
            assert "meta" in data
            assert "results" in data
            assert len(data["results"]) == 1
            assert data["results"][0]["status"] == "success"
            assert "equity_curve" in data["results"][0]
            assert "trades" in data["results"][0]
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)

    def test_success_multiple_groups(self, client):
        """多参数组批量回测，结果顺序与请求一致"""
        prices = [100.0] * 50
        df = _make_df(prices)

        client.app.dependency_overrides[get_v2_backtest_service] = lambda: _make_service(df)
        try:
            request = self._batch_request(param_groups=[
                {"id": "g1", "name": "保守", "params": {"short_period": 10, "long_period": 30}},
                {"id": "g2", "name": "激进", "params": {"short_period": 5, "long_period": 10}},
                {"id": "g3", "name": "默认", "params": {"short_period": 5, "long_period": 20}},
            ])
            response = client.post("/api/v1/backtest/technical/batch", json=request)

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 3
            assert data["results"][0]["group"]["id"] == "g1"
            assert data["results"][1]["group"]["id"] == "g2"
            assert data["results"][2]["group"]["id"] == "g3"
            assert all(r["status"] == "success" for r in data["results"])
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)

    def test_strategy_not_found_returns_error_status(self, client):
        """策略不存在返回 HTTP 200 + status=error"""
        prices = [100.0] * 50
        df = _make_df(prices)

        client.app.dependency_overrides[get_v2_backtest_service] = lambda: _make_service(df)
        try:
            request = self._batch_request(strategy_id="nonexistent")
            response = client.post("/api/v1/backtest/technical/batch", json=request)

            assert response.status_code == 200
            data = response.json()
            assert data["results"][0]["status"] == "error"
            assert data["results"][0].get("stock_result") is None
            assert "策略未找到" in data["results"][0]["error_message"]
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)

    def test_param_validation_error_returns_error_status(self, client):
        """参数校验失败返回 HTTP 200 + status=error"""
        prices = [100.0] * 50
        df = _make_df(prices)

        client.app.dependency_overrides[get_v2_backtest_service] = lambda: _make_service(df)
        try:
            request = self._batch_request(param_groups=[
                {"id": "g1", "name": "错误参数", "params": {"short_period": 30, "long_period": 5}}
            ])
            response = client.post("/api/v1/backtest/technical/batch", json=request)

            assert response.status_code == 200
            data = response.json()
            assert data["results"][0]["status"] == "error"
            assert data["results"][0].get("stock_result") is None
            assert data["results"][0]["error_message"] is not None
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)

    def test_isolation_one_group_error(self, client):
        """异常隔离：1 组失败，其他组正常"""
        prices = [100.0] * 50
        df = _make_df(prices)

        client.app.dependency_overrides[get_v2_backtest_service] = lambda: _make_service(df)
        try:
            request = self._batch_request(param_groups=[
                {"id": "g1", "name": "正常", "params": {"short_period": 5, "long_period": 20}},
                {"id": "g2", "name": "错误", "params": {"short_period": 30, "long_period": 5}},
                {"id": "g3", "name": "正常2", "params": {"short_period": 10, "long_period": 30}},
            ])
            response = client.post("/api/v1/backtest/technical/batch", json=request)

            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 3
            assert data["results"][0]["status"] == "success"
            assert data["results"][1]["status"] == "error"
            assert data["results"][2]["status"] == "success"
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)

    def test_no_data_returns_error_status(self, client):
        """无数据返回 HTTP 200 + status=error"""
        client.app.dependency_overrides[get_v2_backtest_service] = lambda: _make_service(None)
        try:
            response = client.post("/api/v1/backtest/technical/batch", json=self._batch_request())

            assert response.status_code == 200
            data = response.json()
            assert data["results"][0]["status"] == "error"
            assert data["results"][0]["error_message"] == "无数据"
        finally:
            client.app.dependency_overrides.pop(get_v2_backtest_service, None)


class TestFeatureToggleV2:
    """TECHNICAL_BACKTEST_ENABLED=false 时端点返回 503"""

    @staticmethod
    def _disabled_guard():
        raise HTTPException(status_code=503, detail="技术回测功能已禁用")

    def test_strategies_disabled_returns_503(self, client):
        client.app.dependency_overrides[_require_technical_backtest_enabled] = self._disabled_guard
        try:
            response = client.get("/api/v1/backtest/strategies")
            assert response.status_code == 503
            assert response.json()["message"] == "技术回测功能已禁用"
        finally:
            client.app.dependency_overrides.pop(_require_technical_backtest_enabled, None)

    def test_batch_disabled_returns_503(self, client):
        client.app.dependency_overrides[_require_technical_backtest_enabled] = self._disabled_guard
        try:
            response = client.post("/api/v1/backtest/technical/batch", json={
                "codes": ["000001"],
                "start_date": "2024-01-01",
                "end_date": "2024-02-19",
                "eval_window_days": 10,
                "strategy_id": "dual_ma",
                "param_groups": [{"id": "g1", "name": "默认", "params": {"short_period": 5, "long_period": 20}}],
            })
            assert response.status_code == 503
            assert response.json()["message"] == "技术回测功能已禁用"
        finally:
            client.app.dependency_overrides.pop(_require_technical_backtest_enabled, None)
