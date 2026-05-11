# -*- coding: utf-8 -*-
"""模板 API 集成测试

使用临时 SQLite 数据库 + FastAPI TestClient 验证模板 CRUD 端点。
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import create_app
from api.v1.endpoints.technical_backtest import _require_technical_backtest_enabled
from src.config import Config
from src.storage import DatabaseManager


class TestTemplateApi:
    """模板 CRUD 端点测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_tpl_api.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()

        app = create_app()
        self.client = TestClient(app)

        yield

        DatabaseManager.reset_instance()
        Config.reset_instance()
        self._temp_dir.cleanup()

    # ── GET /technical/templates ──────────────────────────

    def test_list_empty_returns_empty_list(self):
        """空数据库返回空模板列表"""
        response = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "dual_ma"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["templates"] == []

    def test_list_after_save_returns_template(self):
        """保存后查询返回已保存模板"""
        self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "dual_ma",
                "name": "默认参数",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {"fast": 5, "slow": 20}}],
            },
        )

        response = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "dual_ma"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["templates"]) == 1
        assert data["templates"][0]["name"] == "默认参数"
        assert data["templates"][0]["strategy_id"] == "dual_ma"
        assert data["templates"][0]["id"] > 0

    def test_list_isolated_by_strategy(self):
        """不同策略模板隔离"""
        self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "dual_ma",
                "name": "MA 模板",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {"short_period": 5}}],
            },
        )
        self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "macd",
                "name": "MACD 模板",
                "params": [{"id": "g2", "name": "G2", "enabled": True, "params": {"fast": 12}}],
            },
        )

        ma_list = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "dual_ma"},
        )
        macd_list = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "macd"},
        )
        assert len(ma_list.json()["templates"]) == 1
        assert len(macd_list.json()["templates"]) == 1

    def test_list_ordered_by_created_at_desc(self):
        """模板按创建时间倒序排列"""
        self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "rsi",
                "name": "旧模板",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {"period": 7}}],
            },
        )
        self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "rsi",
                "name": "新模板",
                "params": [{"id": "g2", "name": "G2", "enabled": True, "params": {"period": 14}}],
            },
        )

        response = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "rsi"},
        )
        templates = response.json()["templates"]
        assert templates[0]["name"] == "新模板"
        assert templates[1]["name"] == "旧模板"

    # ── POST /technical/templates ─────────────────────────

    def test_save_returns_201(self):
        """保存成功返回 201"""
        response = self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "boll",
                "name": "布林模板",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {"period": 20, "stddev": 2}}],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "布林模板"
        assert data["id"] > 0

    def test_save_empty_name_returns_422(self):
        """空名称触发 Pydantic 校验 422"""
        response = self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "dual_ma",
                "name": "",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {"fast": 5}}],
            },
        )
        assert response.status_code == 422

    def test_save_empty_params_returns_422(self):
        """空参数列表触发 Pydantic 校验 422"""
        response = self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "dual_ma",
                "name": "无参数",
                "params": [],
            },
        )
        assert response.status_code == 422

    def test_save_missing_strategy_id_returns_422(self):
        """缺少 strategy_id 触发 Pydantic 校验 422"""
        response = self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "name": "无策略ID",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {}}],
            },
        )
        assert response.status_code == 422

    def test_save_complex_params_roundtrip(self):
        """复杂参数 JSON 往返保真"""
        params = [
            {"id": "g1", "name": "激进", "enabled": True, "params": {"fast": 3, "slow": 8}},
            {"id": "g2", "name": "保守", "enabled": True, "params": {"fast": 10, "slow": 50}},
            {"id": "g3", "name": "仅观察", "enabled": False, "params": {"fast": 20, "slow": 60}},
        ]
        save_resp = self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "dual_ma",
                "name": "三参数组",
                "params": params,
            },
        )
        assert save_resp.status_code == 201
        saved = save_resp.json()

        list_resp = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "dual_ma"},
        )
        got = list_resp.json()["templates"][0]
        assert len(got["params"]) == 3
        assert got["params"][0]["id"] == "g1"
        assert got["params"][0]["params"]["fast"] == 3
        assert got["params"][2]["enabled"] is False

    # ── DELETE /technical/templates/{id} ──────────────────

    def test_delete_existing_returns_204(self):
        """删除存在模板返回 204"""
        save_resp = self.client.post(
            "/api/v1/backtest/technical/templates",
            json={
                "strategy_id": "boll",
                "name": "待删除",
                "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {}}],
            },
        )
        template_id = save_resp.json()["id"]

        response = self.client.delete(f"/api/v1/backtest/technical/templates/{template_id}")
        assert response.status_code == 204

        # 确认已删除
        list_resp = self.client.get(
            "/api/v1/backtest/technical/templates",
            params={"strategy_id": "boll"},
        )
        assert list_resp.json()["templates"] == []

    def test_delete_nonexistent_returns_404(self):
        """删除不存在模板返回 404"""
        response = self.client.delete("/api/v1/backtest/technical/templates/99999")
        assert response.status_code == 404
        detail = response.json()
        assert "not_found" in detail.get("error", "")


class TestTemplateFeatureToggle:
    """TECHNICAL_BACKTEST_ENABLED=false 时模板端点返回 503"""

    @staticmethod
    def _disabled_guard():
        raise HTTPException(status_code=503, detail="技术回测功能已禁用")

    @pytest.fixture(autouse=True)
    def setup(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_tpl_toggle.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()

        app = create_app()
        self.client = TestClient(app)

        yield

        DatabaseManager.reset_instance()
        Config.reset_instance()
        self._temp_dir.cleanup()

    def test_list_disabled_returns_503(self):
        """特性开关关闭时 GET /templates 返回 503"""
        self.client.app.dependency_overrides[_require_technical_backtest_enabled] = self._disabled_guard
        try:
            response = self.client.get(
                "/api/v1/backtest/technical/templates",
                params={"strategy_id": "dual_ma"},
            )
            assert response.status_code == 503
        finally:
            self.client.app.dependency_overrides.pop(_require_technical_backtest_enabled, None)

    def test_save_disabled_returns_503(self):
        """特性开关关闭时 POST /templates 返回 503"""
        self.client.app.dependency_overrides[_require_technical_backtest_enabled] = self._disabled_guard
        try:
            response = self.client.post(
                "/api/v1/backtest/technical/templates",
                json={
                    "strategy_id": "dual_ma",
                    "name": "测试",
                    "params": [{"id": "g1", "name": "G1", "enabled": True, "params": {}}],
                },
            )
            assert response.status_code == 503
        finally:
            self.client.app.dependency_overrides.pop(_require_technical_backtest_enabled, None)

    def test_delete_disabled_returns_503(self):
        """特性开关关闭时 DELETE /templates/{id} 返回 503"""
        self.client.app.dependency_overrides[_require_technical_backtest_enabled] = self._disabled_guard
        try:
            response = self.client.delete("/api/v1/backtest/technical/templates/1")
            assert response.status_code == 503
        finally:
            self.client.app.dependency_overrides.pop(_require_technical_backtest_enabled, None)
