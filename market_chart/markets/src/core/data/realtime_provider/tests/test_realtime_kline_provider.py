"""
RealtimeKlineProvider 单元测试

职责：实时日/周/月K线获取，周/月需要聚合历史+合并当日。
测试重点：
- 日线直接返回
- 周/月线的历史获取 + 聚合 + 合并
- 新周期第一天判断
- 交易时段判断（盘后返回空）
- 异常兜底
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.share.market.market_enums import TradingPhase

from ..realtime_kline_provider import RealtimeKlineProvider
from ..types import RealtimeKline


class TestRealtimeKlineProviderDaily:
    """日K线测试"""

    def test_daily_trading(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading):
        """盘中获取日K — 直接返回实时行情"""
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
        )
        result = provider.get_realtime_kline("600519", period="daily")

        assert result is not None
        assert result.open == 1790.0
        assert result.high == 1810.0
        assert result.low == 1785.0
        assert result.close == 1800.0
        assert result.volume == 100000
        assert result.should_poll is True
        assert result.trading_phase == TradingPhase.TRADING.value

    def test_daily_after_close(self, mock_history_provider, mock_quote_fetcher, mock_calendar_after_close):
        """盘后获取日K — 返回空结构，should_poll=False"""
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_after_close,
        )
        result = provider.get_realtime_kline("600519", period="daily")

        assert result is not None
        assert result.open is None
        assert result.close is None
        assert result.should_poll is False
        assert result.trading_phase == TradingPhase.AFTER_CLOSE.value

    def test_daily_quote_none(self, mock_history_provider, mock_quote_fetcher_fail, mock_calendar_trading):
        """实时行情不可用 — 返回空结构但继续轮询"""
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher_fail,
            calendar=mock_calendar_trading,
        )
        result = provider.get_realtime_kline("600519", period="daily")

        assert result is not None
        assert result.open is None
        assert result.should_poll is True

    def test_daily_quote_incomplete(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading):
        """实时行情缺少关键字段 — 视为不可用"""
        mock_quote_fetcher.get_realtime_quote.return_value = MagicMock(
            price=None,  # 缺少 price
            open_price=1790.0,
        )
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
        )
        result = provider.get_realtime_kline("600519", period="daily")

        assert result is not None
        assert result.open is None
        assert result.should_poll is True


class TestRealtimeKlineProviderWeekly:
    """周K线测试"""

    def test_weekly_merge(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading, mock_bar_aggregator):
        """周线：历史聚合 + 合并当日"""
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=mock_bar_aggregator,
        )
        result = provider.get_realtime_kline("600519", period="weekly")

        assert result is not None
        assert result.should_poll is True

    def test_weekly_new_period(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading, mock_bar_aggregator):
        """周线：新周期第一天 → 当日K柱即为新周期第一个K柱"""
        # 设置历史最后一个K柱为上周
        mock_bar_aggregator.daily_to_weekly.return_value = pd.DataFrame({
            "trade_date": pd.to_datetime(["2026-05-05"]),  # 上周
            "open": [1750.0],
            "high": [1770.0],
            "low": [1740.0],
            "close": [1760.0],
            "volume": [100000],
        })

        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=mock_bar_aggregator,
        )
        result = provider.get_realtime_kline("600519", period="weekly")

        # 新周期应返回当日K柱
        assert result is not None
        assert result.close == 1800.0  # 当日收盘价

    def test_weekly_no_history(self, mock_history_provider_empty, mock_quote_fetcher, mock_calendar_trading, mock_bar_aggregator):
        """周线：无历史数据 → 返回当日K柱"""
        provider = RealtimeKlineProvider(
            mock_history_provider_empty,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=mock_bar_aggregator,
        )
        result = provider.get_realtime_kline("600519", period="weekly")

        assert result is not None
        assert result.close == 1800.0

    def test_weekly_empty_aggregation(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading):
        """周线：历史聚合结果为空 → 返回当日K柱"""
        aggregator = MagicMock()
        aggregator.daily_to_weekly.return_value = pd.DataFrame()  # 空

        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=aggregator,
        )
        result = provider.get_realtime_kline("600519", period="weekly")

        assert result is not None
        assert result.close == 1800.0


class TestRealtimeKlineProviderMonthly:
    """月K线测试"""

    def test_monthly_merge(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading, mock_bar_aggregator):
        """月线：历史聚合 + 合并当日"""
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=mock_bar_aggregator,
        )
        result = provider.get_realtime_kline("600519", period="monthly")

        assert result is not None
        assert result.should_poll is True

    def test_monthly_new_period(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading, mock_bar_aggregator):
        """月线：新月份第一天 → 当日K柱即为新月第一个K柱"""
        mock_bar_aggregator.daily_to_monthly.return_value = pd.DataFrame({
            "trade_date": pd.to_datetime(["2026-04-01"]),  # 上月
            "open": [1600.0],
            "high": [1700.0],
            "low": [1550.0],
            "close": [1680.0],
            "volume": [1000000],
        })

        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=mock_bar_aggregator,
        )
        result = provider.get_realtime_kline("600519", period="monthly")

        assert result is not None
        assert result.close == 1800.0


class TestRealtimeKlineProviderMerge:
    """合并逻辑测试（核心业务规则）"""

    def test_merge_normal(self):
        """正常合并：high取最大，low取最小，close用实时，volume相加"""
        period_bar = pd.Series({
            "open": 1780.0,
            "high": 1800.0,
            "low": 1770.0,
            "close": 1795.0,
            "volume": 100000,
        })
        realtime = RealtimeKline(
            date="2026-05-14",
            open=1790.0,
            high=1810.0,
            low=1785.0,
            close=1800.0,
            volume=50000,
            turnover_rate=0.5,
            trading_phase="trading",
            should_poll=True,
        )

        result = RealtimeKlineProvider._merge_realtime_to_period(period_bar, realtime)

        assert result["open"] == 1780.0
        assert result["high"] == 1810.0
        assert result["low"] == 1770.0
        assert result["close"] == 1800.0
        assert result["volume"] == 150000

    def test_merge_realtime_high_none(self):
        """实时 high 为 None → 使用历史 high"""
        period_bar = pd.Series({
            "open": 1780.0,
            "high": 1800.0,
            "low": 1770.0,
            "close": 1795.0,
            "volume": 100000,
        })
        realtime = RealtimeKline(
            date="2026-05-14",
            open=1790.0,
            high=None,
            low=None,
            close=None,
            volume=0,
            turnover_rate=None,
            trading_phase="trading",
            should_poll=True,
        )

        result = RealtimeKlineProvider._merge_realtime_to_period(period_bar, realtime)

        assert result["high"] == 1800.0
        assert result["low"] == 1770.0
        assert result["close"] == 1795.0

    def test_merge_period_volume_none(self):
        """历史 volume 为 None → 视为 0"""
        period_bar = pd.Series({
            "open": 1780.0,
            "high": 1800.0,
            "low": 1770.0,
            "close": 1795.0,
            "volume": None,
        })
        realtime = RealtimeKline(
            date="2026-05-14",
            open=1790.0,
            high=1810.0,
            low=1785.0,
            close=1800.0,
            volume=50000,
            turnover_rate=0.5,
            trading_phase="trading",
            should_poll=True,
        )

        result = RealtimeKlineProvider._merge_realtime_to_period(period_bar, realtime)

        assert result["volume"] == 50000


class TestRealtimeKlineProviderNewPeriod:
    """新周期检测测试"""

    def test_same_day(self):
        """同一天 → 不是新周期"""
        today = pd.Timestamp("2026-05-14")
        last = pd.Timestamp("2026-05-14")
        assert RealtimeKlineProvider._is_new_period(today, last, "weekly") is False
        assert RealtimeKlineProvider._is_new_period(today, last, "monthly") is False

    def test_weekly_same_week(self):
        """同一周不同天 → 不是新周期"""
        today = pd.Timestamp("2026-05-14")  # 周四
        last = pd.Timestamp("2026-05-12")  # 周二
        assert RealtimeKlineProvider._is_new_period(today, last, "weekly") is False

    def test_weekly_new_week(self):
        """不同周 → 是新周期"""
        today = pd.Timestamp("2026-05-11")  # 周一，第20周
        last = pd.Timestamp("2026-05-10")  # 上周日，第19周
        assert RealtimeKlineProvider._is_new_period(today, last, "weekly") is True

    def test_monthly_same_month(self):
        """同一月 → 不是新周期"""
        today = pd.Timestamp("2026-05-14")
        last = pd.Timestamp("2026-05-01")
        assert RealtimeKlineProvider._is_new_period(today, last, "monthly") is False

    def test_monthly_new_month(self):
        """不同月 → 是新周期"""
        today = pd.Timestamp("2026-05-01")
        last = pd.Timestamp("2026-04-30")
        assert RealtimeKlineProvider._is_new_period(today, last, "monthly") is True


class TestRealtimeKlineProviderPeriodStart:
    """周期起始日期计算"""

    def test_weekly_start(self):
        """本周一"""
        result = RealtimeKlineProvider._get_period_start("weekly", pd.Timestamp("2026-05-14"))
        assert result == pd.Timestamp("2026-05-11")  # 周一是5月11日

    def test_monthly_start(self):
        """本月1日"""
        result = RealtimeKlineProvider._get_period_start("monthly", pd.Timestamp("2026-05-14"))
        assert result == pd.Timestamp("2026-05-01")

    def test_daily_start(self):
        """日线返回当天"""
        result = RealtimeKlineProvider._get_period_start("daily", pd.Timestamp("2026-05-14"))
        assert result == pd.Timestamp("2026-05-14")


class TestRealtimeKlineProviderEdgeCases:
    """边界条件测试"""

    def test_exception_returns_none(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading):
        """严重异常时返回 None"""
        mock_quote_fetcher.get_realtime_quote.side_effect = RuntimeError("boom")
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
        )
        result = provider.get_realtime_kline("600519", period="daily")

        assert result is None

    def test_no_calendar_uses_market_time_utils(self, mock_history_provider, mock_quote_fetcher):
        """无 calendar 时使用 MarketTimeUtils"""
        provider = RealtimeKlineProvider(mock_history_provider, mock_quote_fetcher)
        result = provider.get_realtime_kline("600519", period="daily")

        assert result is not None
        assert "trading_phase" in result.to_dict()

    def test_realtime_kline_to_dict(self):
        """RealtimeKline.to_dict() 输出完整性"""
        kline = RealtimeKline(
            date="2026-05-14",
            open=1790.0,
            high=1810.0,
            low=1785.0,
            close=1800.0,
            volume=100000,
            turnover_rate=0.5,
            trading_phase="trading",
            should_poll=True,
        )
        d = kline.to_dict()

        assert d["date"] == "2026-05-14"
        assert d["open"] == 1790.0
        assert d["close"] == 1800.0
        assert d["should_poll"] is True

    def test_realtime_kline_empty(self):
        """RealtimeKline.empty() 工厂方法"""
        kline = RealtimeKline.empty(
            trade_date="2026-05-14",
            trading_phase="after_close",
            should_poll=False,
        )

        assert kline.date == "2026-05-14"
        assert kline.open is None
        assert kline.close is None
        assert kline.volume == 0
        assert kline.should_poll is False

    def test_realtime_kline_from_quote(self, mock_quote):
        """RealtimeKline.from_quote() 工厂方法"""
        kline = RealtimeKline.from_quote(
            quote=mock_quote,
            trade_date="2026-05-14",
            trading_phase="trading",
            should_poll=True,
        )

        assert kline.open == 1790.0
        assert kline.close == 1800.0
        assert kline.volume == 100000

    def test_invalid_period_raises(self, mock_history_provider, mock_quote_fetcher, mock_calendar_trading, mock_bar_aggregator):
        """不支持的周期 → ValueError"""
        provider = RealtimeKlineProvider(
            mock_history_provider,
            mock_quote_fetcher,
            calendar=mock_calendar_trading,
            bar_aggregator=mock_bar_aggregator,
        )
        with pytest.raises(ValueError, match="不支持的周期"):
            provider._build_period_kline("600519", "quarterly", RealtimeKline.empty("", "", False), pd.Timestamp("2026-05-14"))
