"""市场数据类型定义

从 temp/markets/src/core/share/market/data_types.py 整包移植
适配当前项目，移除深层依赖。
"""

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


@dataclass
class OHLCVRecord:
    """单条OHLCV数据记录"""

    date: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class PriceData:
    """标准价格数据结构"""

    records: List[OHLCVRecord]
    symbol: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    count: int
    needs_realtime_kline: bool = False

    def __post_init__(self):
        if self.records is not None:
            if not isinstance(self.records, list):
                raise ValueError("records must be a list of OHLCVRecord")
            if len(self.records) != self.count:
                # 允许空数据时不严格检查
                if self.count != 0:
                    raise ValueError("count must match the number of records")

    def to_dataframe(self) -> pd.DataFrame:
        if not self.records:
            return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        data = []
        for record in self.records:
            data.append({
                'date': record.date,
                'open': record.open,
                'high': record.high,
                'low': record.low,
                'close': record.close,
                'volume': record.volume,
            })
        return pd.DataFrame(data)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, symbol: str = "") -> 'PriceData':
        required_columns = {'date', 'open', 'high', 'low', 'close', 'volume'}
        if not required_columns.issubset(set(df.columns)):
            raise ValueError(f"DataFrame must contain columns: {required_columns}")
        records = []
        for _, row in df.iterrows():
            record = OHLCVRecord(
                date=pd.to_datetime(row['date']),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
            )
            records.append(record)
        now = pd.Timestamp.now()
        return cls(
            records=records,
            symbol=symbol,
            start_date=records[0].date if records else now,
            end_date=records[-1].date if records else now,
            count=len(records),
        )


@dataclass
class IntradayTickRecord:
    """分时Tick数据记录（1分钟级别）"""

    time: str
    price: float
    volume: int
    avg_price: float


@dataclass
class OrderBookLevel:
    """盘口档位数据"""

    price: float
    volume: int


@dataclass
class TradeDetailRecord:
    """成交明细记录（逐笔成交）"""

    time: str
    price: float
    volume: int
    direction: str


@dataclass
class IntradayData:
    """分时图完整数据结构"""

    symbol: str
    name: str
    current_price: float
    yesterday_close: float
    change: float
    change_percent: float
    ticks: List['IntradayTickRecord']
    order_book_bids: List['OrderBookLevel']
    order_book_asks: List['OrderBookLevel']
    trade_records: List['TradeDetailRecord']
    trade_date: pd.Timestamp
    order_book_message: str = ''
    trade_records_message: str = ''
    is_index: bool = False
    should_poll: bool = False


@dataclass
class TickRange:
    """Tick 数据时间范围"""

    start_time: pd.Timestamp
    end_time: pd.Timestamp
    period_seconds: int = 5

    def get_tick_count(self) -> int:
        """计算时间范围内的tick数量"""
        total_seconds = int((self.end_time - self.start_time).total_seconds())
        return (total_seconds // self.period_seconds) + 1

    @classmethod
    def from_trading_phase(cls, trading_phase: 'TradingPhase', trade_date: pd.Timestamp,
                           current_time: Optional[pd.Timestamp] = None) -> 'TickRange':
        """根据交易时段创建 TickRange"""
        from src.chart_legacy.market_enums import TradingPhase

        if current_time is None:
            current_time = pd.Timestamp.now()

        if isinstance(trade_date, str):
            trade_date = pd.to_datetime(trade_date)

        trade_date_str = trade_date.strftime('%Y-%m-%d')

        if trading_phase.value == 'after_close':
            start_time = pd.Timestamp(f"{trade_date_str} 09:30:00")
            end_time = pd.Timestamp(f"{trade_date_str} 15:00:00")
        elif trading_phase.value == 'before_open':
            start_time = pd.Timestamp(f"{trade_date_str} 09:30:00")
            end_time = start_time
        else:
            start_time = pd.Timestamp(f"{trade_date_str} 09:30:00")
            end_time = min(current_time, pd.Timestamp(f"{trade_date_str} 15:00:00"))

        return cls(start_time=start_time, end_time=end_time, period_seconds=5)
