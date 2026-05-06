"""K线聚合器测试

验证 BarAggregator 将日线正确聚合为周线/月线，
并正确过滤未完成的当前周/月。

输入 DataFrame 列遵循事实标准：
trade_date, open, high, low, close, volume, amount
"""

import pandas as pd
import pytest

from src.data_provider.interfaces import IBarAggregator


class TestBarAggregator:
    """BarAggregator 功能测试"""

    @pytest.fixture
    def aggregator(self):
        from src.data_provider.bar_aggregator import BarAggregator

        return BarAggregator()

    def test_implements_protocol(self, aggregator):
        assert isinstance(aggregator, IBarAggregator)

    def test_daily_to_weekly_basic(self, aggregator):
        """5 个交易日聚合为 1 条周线"""
        df = pd.DataFrame({
            "trade_date": pd.date_range("2024-10-08", periods=5, freq="D"),  # 周二到周六，但只取交易日
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [105.0, 106.0, 107.0, 108.0, 109.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [101.0, 102.0, 103.0, 104.0, 105.0],
            "volume": [1000, 2000, 3000, 4000, 5000],
            "amount": [100000, 200000, 300000, 400000, 500000],
        })
        # 注意：实际应只有 10/8-10/11 是交易日（周五），10/12 是周六
        # 但为了简化测试，直接测试 resample 逻辑
        df = df.head(4)  # 只取 10/08-10/11（周二到周五）
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        weekly = aggregator.daily_to_weekly(df)

        assert len(weekly) == 1
        assert weekly.iloc[0]["open"] == 100.0   # first
        assert weekly.iloc[0]["high"] == 108.0   # max
        assert weekly.iloc[0]["low"] == 99.0     # min
        assert weekly.iloc[0]["close"] == 104.0  # last
        assert weekly.iloc[0]["volume"] == 10000  # sum
        assert weekly.iloc[0]["amount"] == 1000000  # sum

    def test_daily_to_monthly_basic(self, aggregator):
        """多交易日聚合为月线"""
        df = pd.DataFrame({
            "trade_date": pd.date_range("2024-10-01", periods=10, freq="D"),
            "open": [float(i) for i in range(10)],
            "high": [float(i + 5) for i in range(10)],
            "low": [float(i) for i in range(10)],
            "close": [float(i + 1) for i in range(10)],
            "volume": [1000] * 10,
            "amount": [100000] * 10,
        })
        df = df.head(4)  # 只取几天
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        monthly = aggregator.daily_to_monthly(df)

        assert len(monthly) == 1
        assert monthly.iloc[0]["open"] == 0.0    # first
        assert monthly.iloc[0]["high"] == 8.0    # max (4 days: 5,6,7,8)
        assert monthly.iloc[0]["low"] == 0.0     # min
        assert monthly.iloc[0]["close"] == 4.0   # last
        assert monthly.iloc[0]["volume"] == 4000  # sum

    def test_filter_complete_periods_weekly(self, aggregator):
        """过滤未完成的当前周"""
        # 2024-10-14 是周一，10-15 周二
        # 如果 today=10-15（周二），当周不完整，应过滤掉
        df = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-07"), pd.Timestamp("2024-10-14")],
            "open": [100.0, 105.0],
            "high": [110.0, 115.0],
            "low": [95.0, 100.0],
            "close": [108.0, 112.0],
            "volume": [5000, 3000],
            "amount": [500000, 300000],
        })
        today = pd.Timestamp("2024-10-15", tz="Asia/Shanghai")

        filtered = aggregator.filter_complete_periods(df, "weekly", today)

        # 10/07 那周已完成，10/14 当周未完成
        assert len(filtered) == 1
        assert filtered.iloc[0]["trade_date"].strftime("%Y-%m-%d") == "2024-10-07"

    def test_filter_complete_periods_monthly(self, aggregator):
        """过滤未完成的当前月"""
        df = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-09-01"), pd.Timestamp("2024-10-01")],
            "open": [100.0, 105.0],
            "high": [110.0, 115.0],
            "low": [95.0, 100.0],
            "close": [108.0, 112.0],
            "volume": [5000, 3000],
            "amount": [500000, 300000],
        })
        # today=10/15，10月不完整
        today = pd.Timestamp("2024-10-15", tz="Asia/Shanghai")

        filtered = aggregator.filter_complete_periods(df, "monthly", today)

        assert len(filtered) == 1
        assert filtered.iloc[0]["trade_date"].strftime("%Y-%m-%d") == "2024-09-01"

    def test_empty_dataframe(self, aggregator):
        """空 DataFrame 应安全返回"""
        df = pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])
        weekly = aggregator.daily_to_weekly(df)
        assert len(weekly) == 0

        monthly = aggregator.daily_to_monthly(df)
        assert len(monthly) == 0


class TestBarAggregatorEdgeCases:
    """边界条件"""

    @pytest.fixture
    def aggregator(self):
        from src.data_provider.bar_aggregator import BarAggregator
        return BarAggregator()

    def test_single_day_to_weekly(self, aggregator):
        """单条日线转周线"""
        agg = aggregator
        df = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-08")],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [102.0],
            "volume": [1000],
            "amount": [100000],
        })
        weekly = agg.daily_to_weekly(df)
        assert len(weekly) == 1
        assert weekly.iloc[0]["open"] == 100.0
