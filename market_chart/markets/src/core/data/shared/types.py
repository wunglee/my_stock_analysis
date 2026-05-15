"""
共享数据类型

从 core.share.market.data_types 迁移而来，
为 history_provider 和 realtime_provider 提供统一的数据结构。
"""

from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class OHLCVRecord:
    """单条OHLCV数据记录

    数据标准：
    - date: pd.Timestamp 类型，交易日期时间
    - open: float，开盘价
    - high: float，最高价
    - low: float，最低价
    - close: float，收盘价
    - volume: float，成交量
    """
    date: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class PriceData:
    """标准价格数据结构

    属性：
        records: List[OHLCVRecord] - OHLCV数据记录列表
        symbol: str - 证券代码
        start_date: pd.Timestamp - 开始日期
        end_date: pd.Timestamp - 结束日期
        count: int - 记录数量
        needs_realtime_kline: bool - 是否需要获取实时K线
    """
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
                self.count = len(self.records)

    def to_dataframe(self) -> pd.DataFrame:
        """转换为DataFrame格式"""
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
                'volume': record.volume
            })
        return pd.DataFrame(data)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, symbol: str = "") -> 'PriceData':
        """从DataFrame创建PriceData对象"""
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
                volume=float(row['volume'])
            )
            records.append(record)

        start_date = records[0].date if records else pd.Timestamp.now()
        end_date = records[-1].date if records else pd.Timestamp.now()

        return cls(
            records=records,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            count=len(records)
        )
