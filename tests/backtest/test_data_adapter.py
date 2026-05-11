"""测试 CachingDataProviderAdapter"""

import pandas as pd
import pytest

from src.services.backtest.engine.data_adapter import CachingDataProviderAdapter


class MockProvider:
    """模拟 CachingDataProvider"""

    def __init__(self, df: pd.DataFrame | None):
        self._df = df

    def get_daily_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        **kwargs,
    ) -> pd.DataFrame | None:
        return self._df


class TestDataAdapter:
    """数据适配器测试"""

    def _make_df(self, dates: list[str], col_name: str = "trade_date") -> pd.DataFrame:
        return pd.DataFrame({
            col_name: dates,
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000, 2000, 3000],
        })

    def test_column_rename_trade_date_to_date(self):
        """trade_date 列应映射为 date"""
        df = self._make_df(["2024-01-03", "2024-01-01", "2024-01-02"])
        provider = MockProvider(df)
        adapter = CachingDataProviderAdapter(provider)

        result = adapter.get_daily_data("000001", "2024-01-01", "2024-01-03")

        assert result is not None
        assert "date" in result.columns
        assert "trade_date" not in result.columns

    def test_sorting_by_date(self):
        """结果应按 date 升序排列"""
        df = self._make_df(["2024-01-03", "2024-01-01", "2024-01-02"])
        provider = MockProvider(df)
        adapter = CachingDataProviderAdapter(provider)

        result = adapter.get_daily_data("000001", "2024-01-01", "2024-01-03")

        dates = result["date"].tolist()
        assert dates == ["2024-01-01", "2024-01-02", "2024-01-03"]

    def test_date_column_as_string(self):
        """date 列应为字符串类型"""
        df = self._make_df(["2024-01-01", "2024-01-02", "2024-01-03"])
        provider = MockProvider(df)
        adapter = CachingDataProviderAdapter(provider)

        result = adapter.get_daily_data("000001", "2024-01-01", "2024-01-03")

        assert result is not None
        assert result["date"].dtype == object
        assert isinstance(result["date"].iloc[0], str)

    def test_empty_data_returns_none(self):
        """无数据时返回 None"""
        provider = MockProvider(None)
        adapter = CachingDataProviderAdapter(provider)

        result = adapter.get_daily_data("000001", "2024-01-01", "2024-01-02")

        assert result is None

    def test_empty_df_returns_none(self):
        """空 DataFrame 返回 None"""
        provider = MockProvider(pd.DataFrame())
        adapter = CachingDataProviderAdapter(provider)

        result = adapter.get_daily_data("000001", "2024-01-01", "2024-01-02")

        assert result is None

    def test_already_date_column(self):
        """如果原始列已经是 date，不报错"""
        df = self._make_df(["2024-01-02", "2024-01-01", "2024-01-03"], col_name="date")
        provider = MockProvider(df)
        adapter = CachingDataProviderAdapter(provider)

        result = adapter.get_daily_data("000001", "2024-01-01", "2024-01-03")

        assert result is not None
        assert "date" in result.columns
        dates = result["date"].tolist()
        assert dates == ["2024-01-01", "2024-01-02", "2024-01-03"]
