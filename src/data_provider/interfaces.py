"""数据提供层接口定义

采用 Protocol 风格的依赖注入，确保各部分可独立测试。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ITradingCalendar(Protocol):
    """交易日历接口，抽象交易所开休市判断"""

    def is_trading_day(self, date: pd.Timestamp) -> bool:
        """判断某日期是否为交易日"""
        ...

    def trading_days_between(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        """返回闭区间内的所有交易日列表"""
        ...

    def next_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        """返回指定日期的下一个交易日"""
        ...

    def prev_trading_day(self, date: pd.Timestamp) -> pd.Timestamp:
        """返回指定日期的上一个交易日"""
        ...

    def get_effective_trading_date(self, symbol: str) -> pd.Timestamp:
        """根据目标市场盘前/盘后状态，返回最近的有效收盘日。

        盘后且当日是交易日 → 返回当日；
        盘前/交易中/非交易日 → 返回上一个交易日。

        调用方可用此日期作为 end_date 上限，避免请求不存在的未来数据。
        """
        ...


@runtime_checkable
class IBarRepository(Protocol):
    """K线数据仓储接口，抽象数据库读写

    表结构遵循 Tushare/AkShare 事实标准：
    symbol, trade_date, open, high, low, close,
    volume, amount, pre_close, change, pct_chg
    """

    def get_daily_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """读取指定区间的日线数据

        Returns:
            DataFrame 含标准 OHLCV 列；无数据返回 None（非空 DataFrame）
        """
        ...

    def save_daily_bars(self, df: pd.DataFrame, symbol: str) -> int:
        """批量保存日线数据，返回写入条数

        实现需处理 UPSERT：重复 symbol+trade_date 时更新。
        """
        ...

    def get_weekly_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """读取已缓存的完整周线数据（不含当前未完成周）"""
        ...

    def save_weekly_bars(self, df: pd.DataFrame, symbol: str) -> int:
        """批量保存完整周线数据"""
        ...

    def get_monthly_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """读取已缓存的完整月线数据（不含当前未完成月）"""
        ...

    def save_monthly_bars(self, df: pd.DataFrame, symbol: str) -> int:
        """批量保存完整月线数据"""
        ...

    def get_date_range(self, symbol: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """返回 symbol 在数据库中的实际 [最早, 最晚] 交易日，无数据返回 None"""
        ...

    def get_missing_ranges(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """返回请求区间中数据库未覆盖的交易日子区间列表

        结果按时间升序排列，区间互不重叠。
        """
        ...


@runtime_checkable
class IExternalDataSource(Protocol):
    """外部数据源接口，抽象多源自动切换的获取逻辑"""

    def fetch_daily_bars(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """从外部 API 获取日线数据

        内部负责多源遍历与自动故障切换。
        返回标准 OHLCV DataFrame，失败返回 None。
        """
        ...

    def fetch_fundamental(
        self, symbol: str
    ) -> dict | None:
        """获取基本面数据（可选，用于兼容上层接口）"""
        ...

    @property
    def source_name(self) -> str:
        """当前实际命中的数据源名称（用于日志/溯源）"""
        ...


@runtime_checkable
class IBarAggregator(Protocol):
    """K线聚合器接口，日 → 周/月转换"""

    def daily_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """将日线 DataFrame 聚合为周线

        周线规则：周一 open，周内 high/low，周五 close，sum(volume)。
        当前未完成周的数据不应被返回（由调用方过滤）。
        """
        ...

    def daily_to_monthly(self, df: pd.DataFrame) -> pd.DataFrame:
        """将日线 DataFrame 聚合为月线

        月线规则：月初 open，月内 high/low，月末 close，sum(volume)。
        当前未完成月的数据不应被返回（由调用方过滤）。
        """
        ...

    def filter_complete_periods(
        self, df: pd.DataFrame, period: str, today: pd.Timestamp
    ) -> pd.DataFrame:
        """过滤掉当前未完成的周/月数据

        Args:
            period: "weekly" | "monthly"
            today: 当前交易日（用于判断最后一周/月是否完成）
        """
        ...
