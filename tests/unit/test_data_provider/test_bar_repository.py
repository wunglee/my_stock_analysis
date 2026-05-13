"""BarRepository 数据库实现测试

使用内存 SQLite 验证 CRUD、日期范围查询、缺失区间检测。
所有数据结构遵循事实标准。
"""

import pandas as pd
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

from src.data_provider.interfaces import IBarRepository


class _FakeCalendar:
    """内存中的假交易日历，用于测试"""

    def __init__(self, trading_days: list[pd.Timestamp]) -> None:
        self._days = set(trading_days)

    def is_trading_day(self, date: pd.Timestamp) -> bool:
        return date in self._days

    def trading_days_between(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        return sorted([d for d in self._days if start <= d <= end])

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        later = [d for d in self._days if d > date]
        return min(later) if later else date

    def prev_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        earlier = [d for d in self._days if d < date]
        return max(earlier) if earlier else date

    def get_effective_trading_date(self, symbol: str) -> pd.Timestamp:
        return max(self._days)


Base = declarative_base()


class DailyBarModel(Base):
    __tablename__ = "daily_bars"
    symbol = sa.Column(sa.String(16), primary_key=True)
    trade_date = sa.Column(sa.Date, primary_key=True)
    open = sa.Column(sa.Float, nullable=False)
    high = sa.Column(sa.Float, nullable=False)
    low = sa.Column(sa.Float, nullable=False)
    close = sa.Column(sa.Float, nullable=False)
    volume = sa.Column(sa.Float, nullable=False)
    amount = sa.Column(sa.Float, nullable=False)
    pre_close = sa.Column(sa.Float)
    change = sa.Column(sa.Float)
    pct_chg = sa.Column(sa.Float)
    created_at = sa.Column(sa.DateTime, default=sa.func.now())
    updated_at = sa.Column(sa.DateTime, default=sa.func.now(), onupdate=sa.func.now())


class TestSqliteBarRepository:
    """SqliteBarRepository 功能测试"""

    @pytest.fixture
    def engine(self):
        return sa.create_engine("sqlite:///:memory:")

    @pytest.fixture
    def calendar(self):
        # 2024-10-08 到 10-11 是交易日
        days = pd.date_range("2024-10-08", periods=4, freq="D")
        return _FakeCalendar(days.tolist())

    @pytest.fixture
    def repo(self, engine, calendar):
        from src.data_provider.bar_repository import SqliteBarRepository

        return SqliteBarRepository(engine=engine, calendar=calendar)

    def test_save_and_get_daily_bars(self, engine, repo):
        df = pd.DataFrame({
            "trade_date": pd.date_range("2024-10-08", periods=3, freq="D"),
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1000.0, 2000.0, 3000.0],
            "amount": [100000.0, 200000.0, 300000.0],
            "pre_close": [99.0, 100.0, 101.0],
            "change": [1.0, 1.0, 1.0],
            "pct_chg": [1.01, 1.0, 0.99],
        })

        count = repo.save_daily_bars(df, symbol="600519")
        assert count == 3

        result = repo.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-10"),
        )
        assert result is not None
        assert len(result) == 3
        assert list(result.columns) == [
            "symbol", "trade_date", "open", "high", "low", "close",
            "volume", "amount", "pre_close", "change", "pct_chg",
        ]

    def test_get_date_range(self, engine, repo):
        df = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-08"), pd.Timestamp("2024-10-11")],
            "open": [100.0, 103.0],
            "high": [105.0, 108.0],
            "low": [99.0, 102.0],
            "close": [101.0, 104.0],
            "volume": [1000.0, 4000.0],
            "amount": [100000.0, 400000.0],
        })
        repo.save_daily_bars(df, symbol="600519")

        rng = repo.get_date_range("600519")
        assert rng is not None
        assert rng[0].strftime("%Y-%m-%d") == "2024-10-08"
        assert rng[1].strftime("%Y-%m-%d") == "2024-10-11"

    def test_get_missing_ranges_no_data(self, engine, repo, calendar):
        # 数据库为空，整个区间都缺失
        missing = repo.get_missing_ranges(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert len(missing) == 1
        assert missing[0][0].strftime("%Y-%m-%d") == "2024-10-08"
        assert missing[0][1].strftime("%Y-%m-%d") == "2024-10-11"

    def test_get_missing_ranges_partial(self, engine, repo, calendar):
        # 只存了 10/08 和 10/09，缺失 10/10-10/11
        df = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-08"), pd.Timestamp("2024-10-09")],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 2000.0],
            "amount": [100000.0, 200000.0],
        })
        repo.save_daily_bars(df, symbol="600519")

        missing = repo.get_missing_ranges(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert len(missing) == 1
        assert missing[0][0].strftime("%Y-%m-%d") == "2024-10-10"
        assert missing[0][1].strftime("%Y-%m-%d") == "2024-10-11"

    def test_get_missing_ranges_complete(self, engine, repo, calendar):
        # 全部数据已存在
        df = pd.DataFrame({
            "trade_date": pd.date_range("2024-10-08", periods=4, freq="D"),
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [105.0, 106.0, 107.0, 108.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 103.0, 104.0],
            "volume": [1000.0, 2000.0, 3000.0, 4000.0],
            "amount": [100000.0, 200000.0, 300000.0, 400000.0],
        })
        repo.save_daily_bars(df, symbol="600519")

        missing = repo.get_missing_ranges(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert len(missing) == 0

    def test_upsert_duplicate(self, engine, repo):
        # 重复写入应更新而非报错
        df1 = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-08")],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [101.0],
            "volume": [1000.0],
            "amount": [100000.0],
        })
        repo.save_daily_bars(df1, symbol="600519")

        df2 = pd.DataFrame({
            "trade_date": [pd.Timestamp("2024-10-08")],
            "open": [200.0],  # 更新
            "high": [205.0],
            "low": [199.0],
            "close": [201.0],
            "volume": [2000.0],
            "amount": [200000.0],
        })
        repo.save_daily_bars(df2, symbol="600519")

        result = repo.get_daily_bars(
            symbol="600519",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-08"),
        )
        assert result is not None
        assert result.iloc[0]["open"] == 200.0
        assert result.iloc[0]["volume"] == 2000.0

    def test_get_daily_bars_no_data(self, engine, repo):
        result = repo.get_daily_bars(
            symbol="000001",
            start_date=pd.Timestamp("2024-10-08"),
            end_date=pd.Timestamp("2024-10-11"),
        )
        assert result is None
