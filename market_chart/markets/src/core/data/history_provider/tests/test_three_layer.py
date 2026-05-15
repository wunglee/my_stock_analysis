"""
ThreeLayerProvider 单元测试

验证三层缓存编排逻辑：Memory -> DB -> MultiSource，
缺失检测、周期聚合、回写链条。
"""

from unittest.mock import MagicMock, call
import pytest
import pandas as pd

from ..three_layer import ThreeLayerProvider
from ..memory_provider import MemoryCacheProvider


class TestThreeLayerProvider:
    """ThreeLayerProvider 测试类"""

    @pytest.fixture
    def sample_df(self):
        """示例日线数据（8个交易日: 2024-01-01 ~ 2024-01-10）"""
        dates = pd.date_range("2024-01-01", "2024-01-10", freq="B")
        return pd.DataFrame({
            "symbol": "SH600519",
            "trade_date": dates,
            "open": [100.0 + i for i in range(len(dates))],
            "high": [101.0 + i for i in range(len(dates))],
            "low": [99.0 + i for i in range(len(dates))],
            "close": [100.5 + i for i in range(len(dates))],
            "volume": [1000000 + i * 1000 for i in range(len(dates))],
        })

    @pytest.fixture
    def trading_dates(self):
        """2024-01-01 ~ 2024-01-10 的交易日列表"""
        return pd.date_range("2024-01-01", "2024-01-10", freq="B").tolist()

    @pytest.fixture
    def mock_calendar(self, trading_dates):
        """Mock 交易日历 — 根据参数范围过滤返回日期"""
        cal = MagicMock()

        def _trading_days_between(start, end):
            return [
                d for d in trading_dates
                if pd.to_datetime(d).normalize() >= pd.to_datetime(start).normalize()
                and pd.to_datetime(d).normalize() <= pd.to_datetime(end).normalize()
            ]

        cal.trading_days_between.side_effect = _trading_days_between

        def next_trading_day(d):
            # 简单实现：返回下一个自然日（测试中交易日连续，够用）
            return d + pd.Timedelta(days=1)

        cal.next_trading_day.side_effect = next_trading_day
        return cal

    @pytest.fixture
    def mock_bar_aggregator(self):
        """Mock BarAggregator"""
        agg = MagicMock()
        agg.daily_to_weekly = MagicMock()
        agg.daily_to_monthly = MagicMock()
        return agg

    @pytest.fixture
    def provider(self, mock_calendar, mock_bar_aggregator):
        """创建 ThreeLayerProvider，所有依赖注入 mock"""
        memory = MemoryCacheProvider()
        db = MagicMock()
        multi_source = MagicMock()

        return ThreeLayerProvider(
            memory=memory,
            db=db,
            multi_source=multi_source,
            calendar=mock_calendar,
            bar_aggregator=mock_bar_aggregator,
        )

    # === 核心流程测试 ===

    def test_all_memory_hit(self, provider, sample_df, mock_calendar):
        """Memory 全命中，DB 和 MultiSource 不应被调用"""
        provider._memory.set("SH600519", sample_df)

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        provider._db.fetch.assert_not_called()
        provider._multi_source.fetch_daily.assert_not_called()
        # 交易日历被调用用于缺失检测
        mock_calendar.trading_days_between.assert_called_once()

    def test_memory_partial_db_full(self, provider, sample_df, mock_calendar):
        """Memory 部分命中（前4天），DB 补全后4天，MultiSource 不调用"""
        mem_df = sample_df.iloc[:4].copy()
        db_df = sample_df.iloc[4:].copy()

        provider._memory.set("SH600519", mem_df)
        provider._db.fetch.return_value = db_df

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        # DB 被调用补缺失区间（可能被调用多次，每个缺失子区间一次）
        assert provider._db.fetch.call_count >= 1
        provider._multi_source.fetch_daily.assert_not_called()
        # DB 数据回写 Memory
        mem_after = provider._memory.fetch(
            "SH600519", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-10")
        )
        assert mem_after is not None
        assert len(mem_after) == 8

    def test_memory_db_partial_multi_source(self, provider, sample_df, mock_calendar):
        """三层全参与：Memory(前3天) -> DB(中间2天) -> MultiSource(后3天)"""
        mem_df = sample_df.iloc[:3].copy()
        db_df = sample_df.iloc[3:5].copy()
        ext_df = sample_df.iloc[5:].copy()

        provider._memory.set("SH600519", mem_df)
        provider._db.fetch.side_effect = [db_df, None]  # 第一次返回中间2天，第二次（子缺失）返回None
        provider._multi_source.fetch_daily.return_value = ext_df

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        # MultiSource 被调用
        provider._multi_source.fetch_daily.assert_called_once()
        # 外部数据回写 Memory + DB
        provider._db.save.assert_called_once()
        mem_after = provider._memory.fetch(
            "SH600519", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-10")
        )
        assert len(mem_after) == 8

    def test_all_layers_fail_returns_none(self, provider):
        """三层都无数据，返回 None"""
        provider._db.fetch.return_value = None
        provider._multi_source.fetch_daily.return_value = None

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is None

    def test_empty_memory_db_has_data(self, provider, sample_df):
        """Memory 为空，DB 有完整数据，MultiSource 不调用"""
        provider._db.fetch.return_value = sample_df

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        provider._multi_source.fetch_daily.assert_not_called()
        # DB 数据回写 Memory
        mem_after = provider._memory.fetch(
            "SH600519", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-10")
        )
        assert len(mem_after) == 8

    def test_known_empty_skips_external_fetch(self, provider, mock_calendar):
        """Memory 标记 known_empty，跳过 DB 和 MultiSource"""
        provider._memory.mark_known_empty(
            "SH600519", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-10")
        )

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is None
        provider._db.fetch.assert_not_called()
        provider._multi_source.fetch_daily.assert_not_called()

    # === 周期聚合测试 ===

    def test_weekly_aggregation(self, provider, sample_df, mock_bar_aggregator):
        """period='weekly' 时调用 daily_to_weekly"""
        weekly_result = pd.DataFrame({
            "trade_date": pd.to_datetime(["2024-01-01", "2024-01-08"]),
            "open": [100.0, 104.0],
            "close": [103.5, 107.5],
        })
        mock_bar_aggregator.daily_to_weekly.return_value = weekly_result

        provider._memory.set("SH600519", sample_df)

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
            period="weekly",
        )

        assert result is not None
        mock_bar_aggregator.daily_to_weekly.assert_called_once()
        # 验证传入的是完整的日线数据
        call_df = mock_bar_aggregator.daily_to_weekly.call_args[0][0]
        assert len(call_df) == 8

    def test_monthly_aggregation(self, provider, sample_df, mock_bar_aggregator):
        """period='monthly' 时调用 daily_to_monthly"""
        monthly_result = pd.DataFrame({
            "trade_date": pd.to_datetime(["2024-01-31"]),
            "open": [100.0],
            "close": [107.5],
        })
        mock_bar_aggregator.daily_to_monthly.return_value = monthly_result

        provider._memory.set("SH600519", sample_df)

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
            period="monthly",
        )

        assert result is not None
        mock_bar_aggregator.daily_to_monthly.assert_called_once()
        call_df = mock_bar_aggregator.daily_to_monthly.call_args[0][0]
        assert len(call_df) == 8

    def test_daily_period_no_aggregation(self, provider, sample_df, mock_bar_aggregator):
        """period='daily' 时不调用聚合器"""
        provider._memory.set("SH600519", sample_df)

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
            period="daily",
        )

        assert result is not None
        mock_bar_aggregator.daily_to_weekly.assert_not_called()
        mock_bar_aggregator.daily_to_monthly.assert_not_called()

    # === 回写测试 ===

    def test_multi_source_writeback(self, provider, sample_df):
        """MultiSource 命中后回写 Memory 和 DB"""
        mem_df = sample_df.iloc[:4].copy()
        ext_df = sample_df.iloc[4:].copy()

        provider._memory.set("SH600519", mem_df)
        provider._db.fetch.return_value = None
        provider._multi_source.fetch_daily.return_value = ext_df

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        # 外部数据回写 DB（每个缺失子区间命中后都回写）
        assert provider._db.save.call_count >= 1
        # 外部数据回写 Memory
        mem_after = provider._memory.fetch(
            "SH600519", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-10")
        )
        assert len(mem_after) == 8

    # === 边界测试 ===

    def test_memory_exception_falls_back_to_db(self, provider, sample_df):
        """Memory fetch 抛异常，fallback 到 DB"""
        provider._memory = MagicMock()
        provider._memory.fetch.side_effect = RuntimeError("内存错误")
        provider._memory.is_known_empty.return_value = False
        provider._memory.get_earliest_date.return_value = None
        provider._db.fetch.return_value = sample_df

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        provider._db.fetch.assert_called_once()

    def test_db_exception_falls_back_to_multi_source(self, provider, sample_df):
        """DB fetch 抛异常，fallback 到 MultiSource"""
        provider._db.fetch.side_effect = RuntimeError("DB错误")
        provider._multi_source.fetch_daily.return_value = sample_df

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        provider._multi_source.fetch_daily.assert_called_once()
        # 回写 Memory，但 DB 坏了不写入
        mem_after = provider._memory.fetch(
            "SH600519", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-10")
        )
        assert len(mem_after) == 8

    def test_multi_source_exception_returns_partial(self, provider, sample_df):
        """MultiSource 抛异常，返回已有数据"""
        mem_df = sample_df.iloc[:4].copy()
        provider._memory.set("SH600519", mem_df)
        provider._db.fetch.return_value = None
        provider._multi_source.fetch_daily.side_effect = RuntimeError("网络错误")

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        # 返回部分数据（Memory 中的前4天）
        assert result is not None
        assert len(result) == 4

    def test_duplicate_data_dedup(self, provider, sample_df):
        """多层返回重叠数据时去重合并"""
        # Memory 和 DB 都返回完整数据（模拟重复）
        provider._memory.set("SH600519", sample_df)
        provider._db.fetch.return_value = sample_df.copy()

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-10"),
        )

        assert result is not None
        assert len(result) == 8
        # 去重后不应有重复行
        assert len(result) == len(result.drop_duplicates(subset=["trade_date"]))

    def test_single_day_request(self, provider):
        """单日请求"""
        single_day = pd.DataFrame({
            "symbol": "SH600519",
            "trade_date": [pd.Timestamp("2024-01-01")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000000],
        })
        provider._memory.set("SH600519", single_day)

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-01"),
        )

        assert result is not None
        assert len(result) == 1

    def test_no_trading_days_in_range(self, provider, mock_calendar):
        """请求区间内无交易日"""
        mock_calendar.trading_days_between.return_value = []

        result = provider.fetch(
            "SH600519",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-01"),
        )

        # 无交易日 = 无缺失 = 返回 None（因为 memory 也是空的）
        assert result is None
