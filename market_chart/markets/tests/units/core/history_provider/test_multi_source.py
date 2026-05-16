"""
MultiSourceProvider 单元测试

验证多源轮询：优先级顺序、fallback、首次命中即返回。
"""

import pytest
import pandas as pd

from core.data.history_provider.multi_source import MultiSourceProvider
from core.data.history_provider.external_provider import ExternalApiProvider


class TestMultiSourceProvider:
    """MultiSourceProvider 测试类"""

    @pytest.fixture
    def sample_df(self):
        """示例日线数据"""
        return pd.DataFrame({
            'symbol': 'SH600519',
            'trade_date': pd.date_range('2024-01-01', '2024-01-02', freq='B'),
            'open': [100.0, 101.0],
            'high': [101.0, 102.0],
            'low': [99.0, 100.0],
            'close': [100.5, 101.5],
            'volume': [1000000, 1001000],
        })

    def test_first_provider_success_no_fallback(self, sample_df):
        """第一个 provider 成功，后续 provider 不应被调用"""
        call_log = []

        def fetcher_a(symbol, start, end):
            call_log.append('A')
            return sample_df.copy()

        def fetcher_b(symbol, start, end):
            call_log.append('B')
            return None

        provider = MultiSourceProvider([
            ExternalApiProvider("A", fetcher_a),
            ExternalApiProvider("B", fetcher_b),
        ])

        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert result is not None
        assert len(result) == 2
        assert call_log == ['A']  # B 不应被调用

    def test_fallback_to_second_provider(self, sample_df):
        """第一个 provider 失败，fallback 到第二个"""
        def fetcher_a(symbol, start, end):
            return None

        def fetcher_b(symbol, start, end):
            return sample_df.copy()

        provider = MultiSourceProvider([
            ExternalApiProvider("A", fetcher_a),
            ExternalApiProvider("B", fetcher_b),
        ])

        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert result is not None
        assert len(result) == 2

    def test_all_providers_fail_returns_none(self):
        """所有 provider 都失败，返回 None"""
        def fetcher_fail(symbol, start, end):
            return None

        provider = MultiSourceProvider([
            ExternalApiProvider("A", fetcher_fail),
            ExternalApiProvider("B", fetcher_fail),
        ])

        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert result is None

    def test_empty_provider_list_returns_none(self):
        """空 provider 列表返回 None"""
        provider = MultiSourceProvider([])
        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))
        assert result is None

    def test_add_provider(self, sample_df):
        """add_provider 应追加到列表末尾"""
        def fetcher_a(symbol, start, end):
            return None

        def fetcher_b(symbol, start, end):
            return sample_df.copy()

        provider = MultiSourceProvider()
        provider.add_provider(ExternalApiProvider("A", fetcher_a))
        provider.add_provider(ExternalApiProvider("B", fetcher_b))

        assert len(provider.providers) == 2
        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))
        assert result is not None

    def test_second_provider_exception_fallback(self, sample_df):
        """第二个 provider 抛异常，fallback 到第三个"""
        def fetcher_a(symbol, start, end):
            return None

        def fetcher_b(symbol, start, end):
            raise RuntimeError("崩溃")

        def fetcher_c(symbol, start, end):
            return sample_df.copy()

        provider = MultiSourceProvider([
            ExternalApiProvider("A", fetcher_a),
            ExternalApiProvider("B", fetcher_b),
            ExternalApiProvider("C", fetcher_c),
        ])

        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert result is not None
        assert len(result) == 2

    def test_first_provider_empty_df_fallback(self, sample_df):
        """第一个 provider 返回空 DataFrame，应 fallback"""
        def fetcher_a(symbol, start, end):
            return pd.DataFrame()

        def fetcher_b(symbol, start, end):
            return sample_df.copy()

        provider = MultiSourceProvider([
            ExternalApiProvider("A", fetcher_a),
            ExternalApiProvider("B", fetcher_b),
        ])

        result = provider.fetch_daily('SH600519', pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02'))

        assert result is not None

    def test_providers_property_returns_copy(self, sample_df):
        """providers 属性应返回列表副本（外部修改不影响内部）"""
        provider = MultiSourceProvider()
        provider.add_provider(ExternalApiProvider("A", lambda s, st, en: sample_df.copy()))

        providers = provider.providers
        providers.clear()  # 外部修改

        assert len(provider.providers) == 1  # 内部不受影响
