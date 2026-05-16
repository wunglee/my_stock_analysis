"""
DbProvider 单元测试

Mock repository，验证 DbProvider 只调用 daily 方法，
并正确处理 DataFrame/None/空 的返回语义。
"""

from unittest.mock import MagicMock
import pytest
import pandas as pd


class TestDbProvider:
    """DbProvider 测试类"""

    @pytest.fixture
    def mock_repo(self):
        """创建 mock repository（无需导入真实类）"""
        repo = MagicMock()
        # 模拟 SqliteBarRepository 的 daily 方法
        repo.get_daily_bars = MagicMock()
        repo.save_daily_bars = MagicMock()
        return repo

    @pytest.fixture
    def provider(self, mock_repo):
        """创建 DbProvider 实例，注入 mock repo"""
        from core.data.history_provider.db_provider import DbProvider
        return DbProvider(repository=mock_repo)

    @pytest.fixture
    def sample_df(self):
        """创建示例日线数据 DataFrame（含 amount 等扩展列）"""
        dates = pd.date_range('2024-01-01', '2024-01-10', freq='B')
        return pd.DataFrame({
            'symbol': 'SH600519',
            'trade_date': dates,
            'open': [100.0 + i for i in range(len(dates))],
            'high': [101.0 + i for i in range(len(dates))],
            'low': [99.0 + i for i in range(len(dates))],
            'close': [100.5 + i for i in range(len(dates))],
            'volume': [1000000 + i * 1000 for i in range(len(dates))],
            'amount': [5000000 + i * 5000 for i in range(len(dates))],
        })

    # === fetch 测试 ===

    def test_fetch_returns_dataframe(self, provider, mock_repo, sample_df):
        """Repository 返回有数据的 DataFrame，DbProvider 原样返回"""
        mock_repo.get_daily_bars.return_value = sample_df

        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )

        assert result is not None
        assert len(result) == 8
        mock_repo.get_daily_bars.assert_called_once_with(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )

    def test_fetch_returns_none(self, provider, mock_repo):
        """Repository 返回 None，DbProvider 也返回 None"""
        mock_repo.get_daily_bars.return_value = None

        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )

        assert result is None

    def test_fetch_empty_dataframe_returns_none(self, provider, mock_repo):
        """Repository 返回空 DataFrame，DbProvider 转换为 None"""
        mock_repo.get_daily_bars.return_value = pd.DataFrame(
            columns=['symbol', 'trade_date', 'open', 'high', 'low', 'close', 'volume']
        )

        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10')
        )

        assert result is None

    def test_fetch_period_ignored(self, provider, mock_repo):
        """period 参数被忽略（DbProvider 只处理日线）"""
        mock_repo.get_daily_bars.return_value = None

        provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-10'),
            period='weekly'
        )

        # 验证仍然只调用了 get_daily_bars，period 不影响行为
        mock_repo.get_daily_bars.assert_called_once()

    # === save 测试 ===

    def test_save_delegates_to_repo(self, provider, mock_repo, sample_df):
        """save 方法委托给 repository.save_daily_bars"""
        mock_repo.save_daily_bars.return_value = 8

        result = provider.save('SH600519', sample_df)

        assert result == 8
        mock_repo.save_daily_bars.assert_called_once_with(sample_df, 'SH600519')

    def test_save_empty_dataframe(self, provider, mock_repo):
        """save 空 DataFrame 时直接返回 0，不调用 repository"""
        empty_df = pd.DataFrame(columns=['trade_date', 'open', 'high', 'low', 'close', 'volume'])

        result = provider.save('SH600519', empty_df)

        assert result == 0
        mock_repo.save_daily_bars.assert_not_called()

    def test_save_none_returns_zero(self, provider, mock_repo):
        """save None 时返回 0，不调用 repository"""
        result = provider.save('SH600519', None)

        assert result == 0
        mock_repo.save_daily_bars.assert_not_called()

    # === 列名一致性验证 ===

    def test_fetch_returns_trade_date_column(self, provider, mock_repo):
        """返回的 DataFrame 必须包含 trade_date 列"""
        dates = pd.date_range('2024-01-01', '2024-01-03', freq='B')
        df = pd.DataFrame({
            'symbol': 'SH600519',
            'trade_date': dates,
            'open': [100.0, 101.0, 102.0],
            'high': [101.0, 102.0, 103.0],
            'low': [99.0, 100.0, 101.0],
            'close': [100.5, 101.5, 102.5],
            'volume': [1000000, 1001000, 1002000],
            'amount': [5000000, 5005000, 5010000],
        })
        mock_repo.get_daily_bars.return_value = df

        result = provider.fetch(
            'SH600519',
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-03')
        )

        assert 'trade_date' in result.columns
        # symbol 列由 repository 返回，DbProvider 不剥离
        assert 'symbol' in result.columns
