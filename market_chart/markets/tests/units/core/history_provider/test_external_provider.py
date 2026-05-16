"""
ExternalApiProvider 单元测试

验证列名标准化、异常处理、空数据转换。
"""

import pytest
import pandas as pd
import numpy as np

from core.data.history_provider.external_provider import ExternalApiProvider


class TestExternalApiProvider:
    """ExternalApiProvider 测试类"""

    @pytest.fixture
    def sample_raw_df(self):
        """模拟原始 fetcher 返回的 DataFrame（含旧列名 'date'）"""
        dates = pd.date_range('2024-01-01', '2024-01-03', freq='B')
        return pd.DataFrame({
            'date': dates,
            'open': [100.0, 101.0, 102.0],
            'high': [101.0, 102.0, 103.0],
            'low': [99.0, 100.0, 101.0],
            'close': [100.5, 101.5, 102.5],
            'volume': [1000000, 1001000, 1002000],
            'amount': [5000000, 5005000, 5010000],
            'turnover_rate': [0.5, 0.6, 0.7],
        })

    def test_fetch_normalizes_date_column(self, sample_raw_df):
        """旧列名 'date' 应被转换为 'trade_date'"""
        def mock_fetcher(symbol, start, end):
            return sample_raw_df.copy()

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        assert result is not None
        assert 'trade_date' in result.columns
        assert 'date' not in result.columns
        assert len(result) == 3

    def test_fetch_adds_symbol_column(self, sample_raw_df):
        """结果应包含 symbol 列"""
        def mock_fetcher(symbol, start, end):
            return sample_raw_df.copy()

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        assert 'symbol' in result.columns
        assert result['symbol'].iloc[0] == 'SH600519'

    def test_fetch_strips_non_standard_columns(self, sample_raw_df):
        """非标准列（如 ma5, volume_ratio）应被过滤"""
        df = sample_raw_df.copy()
        df['ma5'] = [100, 101, 102]
        df['volume_ratio'] = [1.0, 1.1, 1.2]

        def mock_fetcher(symbol, start, end):
            return df

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        assert 'ma5' not in result.columns
        assert 'volume_ratio' not in result.columns
        assert 'open' in result.columns
        assert 'volume' in result.columns

    def test_fetch_returns_none_when_fetcher_returns_none(self):
        """fetcher 返回 None 时，provider 也返回 None"""
        def mock_fetcher(symbol, start, end):
            return None

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        assert result is None

    def test_fetch_returns_none_when_fetcher_returns_empty(self):
        """fetcher 返回空 DataFrame 时，provider 也返回 None"""
        def mock_fetcher(symbol, start, end):
            return pd.DataFrame()

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        assert result is None

    def test_fetch_handles_exception(self):
        """fetcher 抛出异常时，provider 返回 None 不抛错"""
        def mock_fetcher(symbol, start, end):
            raise RuntimeError("网络错误")

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        assert result is None

    def test_fetch_preserves_existing_trade_date(self):
        """如果原始数据已有 trade_date 列，不应报错"""
        df = pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', '2024-01-02', freq='B'),
            'open': [100.0, 101.0],
            'close': [100.5, 101.5],
            'volume': [1000000, 1001000],
        })

        def mock_fetcher(symbol, start, end):
            return df

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert result is not None
        assert 'trade_date' in result.columns
        assert len(result) == 2

    def test_fetch_keeps_optional_standard_columns(self):
        """可选标准列（如 pre_close, change, pct_chg）应被保留"""
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', '2024-01-02', freq='B'),
            'open': [100.0, 101.0],
            'high': [101.0, 102.0],
            'low': [99.0, 100.0],
            'close': [100.5, 101.5],
            'volume': [1000000, 1001000],
            'pre_close': [99.5, 100.5],
            'change': [1.0, 1.0],
            'pct_chg': [1.01, 1.0],
        })

        def mock_fetcher(symbol, start, end):
            return df

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert 'pre_close' in result.columns
        assert 'change' in result.columns
        assert 'pct_chg' in result.columns

    def test_fetch_sorts_by_date(self):
        """结果应按 trade_date 升序排列"""
        df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-03', '2024-01-01', '2024-01-02']),
            'open': [102.0, 100.0, 101.0],
            'close': [102.5, 100.5, 101.5],
            'volume': [1002000, 1000000, 1001000],
        })

        def mock_fetcher(symbol, start, end):
            return df

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-03'))

        dates = list(result['trade_date'])
        assert dates == sorted(dates)

    def test_name_property(self):
        """name 属性应返回构造时传入的名称"""
        provider = ExternalApiProvider(name="akshare", fetcher=lambda s, st, en: None)
        assert provider.name == "akshare"

    def test_period_parameter_ignored(self, sample_raw_df):
        """period 参数不影响行为"""
        def mock_fetcher(symbol, start, end):
            return sample_raw_df.copy()

        provider = ExternalApiProvider(name="mock", fetcher=mock_fetcher)
        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-03'),
            period='weekly'
        )

        assert result is not None
        assert len(result) == 3
