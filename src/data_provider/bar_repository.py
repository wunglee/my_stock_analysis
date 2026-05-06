"""BarRepository 的 SQLite 实现

表结构遵循 Tushare/AkShare 事实标准：
symbol, trade_date, open, high, low, close, volume, amount, pre_close, change, pct_chg
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import declarative_base, sessionmaker

from src.data_provider.interfaces import IBarRepository, ITradingCalendar

if TYPE_CHECKING:
    from src.storage import DatabaseManager

logger = logging.getLogger(__name__)
Base = declarative_base()


# ------------------------------------------------------------------ #
# ORM Models
# ------------------------------------------------------------------ #
class DailyBar(Base):
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


class WeeklyBar(Base):
    __tablename__ = "weekly_bars"

    symbol = sa.Column(sa.String(16), primary_key=True)
    trade_date = sa.Column(sa.Date, primary_key=True)  # 该周周一日期
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


class MonthlyBar(Base):
    __tablename__ = "monthly_bars"

    symbol = sa.Column(sa.String(16), primary_key=True)
    trade_date = sa.Column(sa.Date, primary_key=True)  # 该月首日日期
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


# ------------------------------------------------------------------ #
# Repository Implementation
# ------------------------------------------------------------------ #
class SqliteBarRepository:
    """SQLite 实现的 K线数据仓储

    Args:
        engine: SQLAlchemy Engine（可以是 :memory: 或文件路径）
        db_manager: DatabaseManager 实例（与 engine 二选一）
        calendar: 交易日历实例（用于缺失区间计算）
    """

    def __init__(
        self,
        engine: sa.Engine | None = None,
        db_manager: "DatabaseManager" | None = None,
        calendar: ITradingCalendar | None = None,
    ) -> None:
        if db_manager is not None:
            self._engine = db_manager._engine
        elif engine is not None:
            self._engine = engine
        else:
            raise ValueError("Either engine or db_manager must be provided")

        self._calendar = calendar
        self._session_factory = sessionmaker(bind=self._engine)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        Base.metadata.create_all(self._engine)

    def _to_date(self, ts: pd.Timestamp) -> date:
        """统一将 pd.Timestamp 转为 Python date"""
        if isinstance(ts, pd.Timestamp):
            return ts.date()
        return ts

    # ------------------------------------------------------------------ #
    # Daily bars
    # ------------------------------------------------------------------ #
    def get_daily_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        start = self._to_date(start_date)
        end = self._to_date(end_date)

        with self._session_factory() as session:
            rows = (
                session.query(DailyBar)
                .filter(DailyBar.symbol == symbol)
                .filter(DailyBar.trade_date >= start)
                .filter(DailyBar.trade_date <= end)
                .order_by(DailyBar.trade_date)
                .all()
            )
            if not rows:
                return None

            data = []
            for r in rows:
                data.append({
                    "symbol": r.symbol,
                    "trade_date": pd.Timestamp(r.trade_date),
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "amount": r.amount,
                    "pre_close": r.pre_close,
                    "change": r.change,
                    "pct_chg": r.pct_chg,
                })
            return pd.DataFrame(data)

    # SQLite bind param 上限安全阈值（每条约10字段，80条≈800参数）
    _CHUNK_SIZE = 80

    def save_daily_bars(self, df: pd.DataFrame, symbol: str) -> int:
        if df.empty:
            return 0

        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

        records = []
        for _, row in df.iterrows():
            records.append({
                "symbol": symbol,
                "trade_date": row["trade_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]),
                "pre_close": float(row["pre_close"]) if "pre_close" in df.columns and pd.notna(row.get("pre_close")) else None,
                "change": float(row["change"]) if "change" in df.columns and pd.notna(row.get("change")) else None,
                "pct_chg": float(row["pct_chg"]) if "pct_chg" in df.columns and pd.notna(row.get("pct_chg")) else None,
            })

        total = 0
        for i in range(0, len(records), self._CHUNK_SIZE):
            chunk = records[i:i + self._CHUNK_SIZE]
            stmt = sqlite_insert(DailyBar).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "trade_date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "amount": stmt.excluded.amount,
                    "pre_close": stmt.excluded.pre_close,
                    "change": stmt.excluded.change,
                    "pct_chg": stmt.excluded.pct_chg,
                    "updated_at": sa.func.now(),
                },
            )
            with self._session_factory() as session:
                session.execute(stmt)
                session.commit()
            total += len(chunk)

        return total

    # ------------------------------------------------------------------ #
    # Weekly / Monthly bars (delegated to generic helpers)
    # ------------------------------------------------------------------ #
    def get_weekly_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        return self._get_period_bars(WeeklyBar, symbol, start_date, end_date)

    def save_weekly_bars(self, df: pd.DataFrame, symbol: str) -> int:
        return self._save_period_bars(WeeklyBar, df, symbol)

    def get_monthly_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        return self._get_period_bars(MonthlyBar, symbol, start_date, end_date)

    def save_monthly_bars(self, df: pd.DataFrame, symbol: str) -> int:
        return self._save_period_bars(MonthlyBar, df, symbol)

    # ------------------------------------------------------------------ #
    # Generic helpers for period bars
    # ------------------------------------------------------------------ #
    def _get_period_bars(
        self,
        model,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        start = self._to_date(start_date)
        end = self._to_date(end_date)

        with self._session_factory() as session:
            rows = (
                session.query(model)
                .filter(model.symbol == symbol)
                .filter(model.trade_date >= start)
                .filter(model.trade_date <= end)
                .order_by(model.trade_date)
                .all()
            )
            if not rows:
                return None

            data = []
            for r in rows:
                data.append({
                    "symbol": r.symbol,
                    "trade_date": pd.Timestamp(r.trade_date),
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "amount": r.amount,
                    "pre_close": r.pre_close,
                    "change": r.change,
                    "pct_chg": r.pct_chg,
                })
            return pd.DataFrame(data)

    def _save_period_bars(self, model, df: pd.DataFrame, symbol: str) -> int:
        if df.empty:
            return 0

        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

        records = []
        for _, row in df.iterrows():
            records.append({
                "symbol": symbol,
                "trade_date": row["trade_date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]),
                "pre_close": float(row["pre_close"]) if "pre_close" in df.columns and pd.notna(row.get("pre_close")) else None,
                "change": float(row["change"]) if "change" in df.columns and pd.notna(row.get("change")) else None,
                "pct_chg": float(row["pct_chg"]) if "pct_chg" in df.columns and pd.notna(row.get("pct_chg")) else None,
            })

        total = 0
        for i in range(0, len(records), self._CHUNK_SIZE):
            chunk = records[i:i + self._CHUNK_SIZE]
            stmt = sqlite_insert(model).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "trade_date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "amount": stmt.excluded.amount,
                    "pre_close": stmt.excluded.pre_close,
                    "change": stmt.excluded.change,
                    "pct_chg": stmt.excluded.pct_chg,
                    "updated_at": sa.func.now(),
                },
            )
            with self._session_factory() as session:
                session.execute(stmt)
                session.commit()
            total += len(chunk)

        return total

    # ------------------------------------------------------------------ #
    # Date range & missing ranges
    # ------------------------------------------------------------------ #
    def get_date_range(self, symbol: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        with self._session_factory() as session:
            min_date = session.query(sa.func.min(DailyBar.trade_date)).filter(
                DailyBar.symbol == symbol
            ).scalar()
            max_date = session.query(sa.func.max(DailyBar.trade_date)).filter(
                DailyBar.symbol == symbol
            ).scalar()

        if min_date is None or max_date is None:
            return None
        return pd.Timestamp(min_date), pd.Timestamp(max_date)

    def get_missing_ranges(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """返回请求区间中数据库未覆盖的交易日子区间列表"""
        # 1. 获取请求区间内的所有交易日
        trading_days = self._calendar.trading_days_between(start_date, end_date)
        if not trading_days:
            return []

        # 2. 获取数据库中已有的日期
        with self._session_factory() as session:
            existing = {
                r[0]
                for r in session.query(DailyBar.trade_date)
                .filter(DailyBar.symbol == symbol)
                .filter(DailyBar.trade_date >= self._to_date(start_date))
                .filter(DailyBar.trade_date <= self._to_date(end_date))
                .all()
            }

        # 3. 找出缺失的交易日
        missing_days = [d for d in trading_days if d.date() not in existing]
        if not missing_days:
            return []

        # 4. 将连续缺失日聚合成区间
        ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        range_start = missing_days[0]
        range_end = missing_days[0]

        for day in missing_days[1:]:
            # 如果与当前区间连续（下一个交易日）
            expected_next = self._calendar.next_trading_day(range_end)
            if day == expected_next:
                range_end = day
            else:
                ranges.append((range_start, range_end))
                range_start = day
                range_end = day

        ranges.append((range_start, range_end))
        return ranges
