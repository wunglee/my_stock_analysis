"""BacktestTemplateRepository 集成测试

使用临时 SQLite 数据库验证模板 CRUD 操作。
"""

import json
import os
import tempfile

import pytest

from src.config import Config
from src.storage import DatabaseManager


class TestBacktestTemplateRepository:
    @pytest.fixture(autouse=True)
    def setup(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_templates.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

        from src.repositories.backtest_template_repo import BacktestTemplateRepository

        self.repo = BacktestTemplateRepository(self.db)

        yield

        DatabaseManager.reset_instance()
        Config.reset_instance()
        self._temp_dir.cleanup()

    def test_list_empty_returns_empty_list(self):
        result = self.repo.list_by_strategy("dual_ma")
        assert result == []

    def test_save_and_list(self):
        params = [{"id": "g1", "name": "Group 1", "params": {"fast": 5, "slow": 20}}]
        self.repo.save("dual_ma", "默认参数", params)

        templates = self.repo.list_by_strategy("dual_ma")
        assert len(templates) == 1
        assert templates[0]["name"] == "默认参数"
        assert templates[0]["strategy_id"] == "dual_ma"
        assert len(templates[0]["params"]) == 1
        assert templates[0]["params"][0]["id"] == "g1"

    def test_save_multiple_same_name(self):
        params = [{"id": "g1", "name": "G1", "params": {"fast": 5, "slow": 20}}]
        self.repo.save("dual_ma", "我的模板", params)
        self.repo.save("dual_ma", "我的模板", params)

        templates = self.repo.list_by_strategy("dual_ma")
        assert len(templates) == 2

    def test_list_isolated_by_strategy(self):
        self.repo.save("dual_ma", "MA 模板", [{"id": "g1", "name": "G1", "params": {}}])
        self.repo.save("macd", "MACD 模板", [{"id": "g2", "name": "G2", "params": {}}])

        assert len(self.repo.list_by_strategy("dual_ma")) == 1
        assert len(self.repo.list_by_strategy("macd")) == 1

    def test_get_existing_template(self):
        params = [{"id": "g1", "name": "G1", "params": {"period": 14}}]
        saved = self.repo.save("rsi", "RSI 模板", params)

        got = self.repo.get(saved["id"])
        assert got is not None
        assert got["name"] == "RSI 模板"
        assert got["strategy_id"] == "rsi"

    def test_get_nonexistent_returns_none(self):
        assert self.repo.get(99999) is None

    def test_delete_existing(self):
        saved = self.repo.save("boll", "布林模板", [{"id": "g1", "name": "G1", "params": {}}])
        assert self.repo.delete(saved["id"]) is True
        assert self.repo.get(saved["id"]) is None

    def test_delete_nonexistent_returns_false(self):
        assert self.repo.delete(99999) is False

    def test_list_ordered_by_created_at_desc(self):
        self.repo.save("dual_ma", "旧模板", [{"id": "g1", "name": "G1", "params": {}}])
        self.repo.save("dual_ma", "新模板", [{"id": "g2", "name": "G2", "params": {}}])

        templates = self.repo.list_by_strategy("dual_ma")
        assert templates[0]["name"] == "新模板"
        assert templates[1]["name"] == "旧模板"

    def test_complex_params_roundtrip(self):
        params = [
            {"id": "g1", "name": "激进", "enabled": True, "params": {"fast": 3, "slow": 8}},
            {"id": "g2", "name": "保守", "enabled": True, "params": {"fast": 10, "slow": 50}},
            {"id": "g3", "name": "仅观察", "enabled": False, "params": {"fast": 20, "slow": 60}},
        ]
        saved = self.repo.save("dual_ma", "三参数组", params)

        got = self.repo.get(saved["id"])
        assert got is not None
        assert len(got["params"]) == 3
        assert got["params"][0]["id"] == "g1"
        assert got["params"][0]["params"]["fast"] == 3
        assert got["params"][2]["enabled"] is False
