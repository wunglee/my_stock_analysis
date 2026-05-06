"""K线聚合器

将日线 DataFrame 聚合为周线/月线。
输入/输出列遵循事实标准：trade_date, open, high, low, close, volume, amount
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# 聚合规则：周线/月线共用
_AGG_RULES = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "amount": "sum",
}

# 可选列：存在时才聚合
_OPTIONAL_COLS = ["pre_close", "change", "pct_chg"]


class BarAggregator:
    """日线 → 周线/月线聚合器

    使用 pandas.resample 按自然周/月聚合。
    不处理缺失交易日（由调用方保证数据连续）。
    """

    # ------------------------------------------------------------------ #
    # IBarAggregator implementation
    # ------------------------------------------------------------------ #
    def daily_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        df = self._normalize(df)
        rules = self._build_rules(df)

        # 按自然周（周一为起点）分组聚合。
        # 使用 groupby 而非 resample：没有数据的周不会产出行，
        # 从根本上避免空周（如春节整周放假）产生 NaN+volume=0 的脏行。
        df["_week_start"] = df.index.map(lambda dt: dt - pd.Timedelta(days=dt.weekday()))
        weekly = df.groupby("_week_start").agg(rules).reset_index()
        weekly = weekly.rename(columns={"_week_start": "trade_date"})
        return weekly

    def daily_to_monthly(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        df = self._normalize(df)
        rules = self._build_rules(df)

        # 按自然月（月末为标签）分组聚合。
        # 使用 groupby 而非 resample：没有数据的月不会产出行，
        # 从根本上避免空月产生 NaN+volume=0 的脏行。
        df["_month_end"] = df.index.map(lambda dt: (dt + pd.offsets.MonthEnd(0)).normalize())
        monthly = df.groupby("_month_end").agg(rules).reset_index()
        monthly = monthly.rename(columns={"_month_end": "trade_date"})
        return monthly

    @staticmethod
    def _week_start(dt: pd.Timestamp) -> pd.Timestamp:
        """返回日期所在周的周一（自然周起点）"""
        return dt - pd.Timedelta(days=dt.weekday())

    def filter_complete_periods(
        self, df: pd.DataFrame, period: str, today: pd.Timestamp
    ) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])

        # 统一转为 naive，避免 aware/naive 比较错误
        if today.tzinfo is not None:
            today = today.tz_localize(None)

        if period == "weekly":
            # 使用自然周起点（周一）判定，避免 isocalendar 跨年周问题
            today_week_start = self._week_start(today)
            df["_week_start"] = df["trade_date"].apply(self._week_start)
            mask = df["_week_start"] != today_week_start
        elif period == "monthly":
            today_month = (today.year, today.month)
            df["_year_month"] = df["trade_date"].apply(lambda d: (d.year, d.month))
            mask = df["_year_month"] != today_month
        else:
            raise ValueError(f"Unsupported period: {period}, expected 'weekly' or 'monthly'")

        drop_col = "_week_start" if period == "weekly" else "_year_month"
        result = df.loc[mask].drop(columns=[drop_col])
        return result.reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """将输入 DataFrame 转换为以 trade_date 为 DatetimeIndex 的格式"""
        df = df.copy()
        if "trade_date" not in df.columns:
            raise ValueError("Input DataFrame must contain 'trade_date' column")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df.set_index("trade_date").sort_index()

    def _build_rules(self, df: pd.DataFrame) -> dict[str, str]:
        """根据实际存在的列构建聚合规则"""
        rules = {}
        for col, rule in _AGG_RULES.items():
            if col in df.columns:
                rules[col] = rule
        # 可选列：存在时按 last 聚合（价格类）或 sum（量类）
        for col in _OPTIONAL_COLS:
            if col in df.columns:
                rules[col] = "last" if col in ("pre_close", "change", "pct_chg") else "sum"
        return rules
