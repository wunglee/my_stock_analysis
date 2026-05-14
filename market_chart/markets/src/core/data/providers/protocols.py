"""  
历史数据提供者协议接口

职责：
- 定义历史数据提供者的标准接口契约
- 支持多种实现（Mock/Real/自定义）的无缝切换
- 为数据模块提供统一的接口规范

设计原则：
- ABC抽象基类，强制子类实现所有抽象方法
- 接口稳定，向后兼容
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Union, Optional

import pandas as pd

# 导入市场数据类型
from core.share.market.data_types import PriceData, OHLCVRecord
# 导入 TradingPhase 枚举
from core.share.market.market_enums import TradingPhase


@dataclass
class IntradayTickRecord:
    """
    分时Tick数据记录（1分钟级别）
    
    属性：
        time: str - 交易时间（HH:MM格式）
        price: float - 当前价格
        volume: int - 成交量（手）
        avg_price: float - 均价
    """
    time: str
    price: float
    volume: int
    avg_price: float


@dataclass
class OrderBookLevel:
    """
    盘口档位数据
    
    属性：
        price: float - 价格
        volume: int - 挂单量（手）
    """
    price: float
    volume: int


@dataclass
class TradeDetailRecord:
    """
    成交明细记录（逐笔成交）
    
    属性：
        time: str - 成交时间（HH:MM:SS格式）
        price: float - 成交价格
        volume: int - 成交量（手）
        direction: str - 买卖方向（'buy'/'sell'）
    """
    time: str
    price: float
    volume: int
    direction: str


@dataclass
class IntradayData:
    """
    分时图完整数据结构
    
    属性：
        symbol: str - 证券代码
        name: str - 证券名称
        current_price: float - 当前价格
        yesterday_close: float - 昨收价
        change: float - 涨跌额
        change_percent: float - 涨跌幅（%）
        ticks: List[IntradayTickRecord] - 分时tick数据列表
        order_book_bids: List[OrderBookLevel] - 买盘档位（从高到低）
        order_book_asks: List[OrderBookLevel] - 卖盘档位（从低到高）
        trade_records: List[TradeDetailRecord] - 成交明细列表（逐笔成交）
        trade_date: pd.Timestamp - 交易日期（YYYY-MM-DD）
        order_book_message: str - 盘口数据提示信息（如果为空）
        trade_records_message: str - 成交明细提示信息（如果为空）
        is_index: bool - 是否为指数（True=指数不可交易，False=个股可交易）
        should_poll: bool - 是否应该轮询（盘前或盘中为True）
    """
    symbol: str
    name: str
    current_price: float
    yesterday_close: float
    change: float
    change_percent: float
    ticks: List[IntradayTickRecord]
    order_book_bids: List[OrderBookLevel]
    order_book_asks: List[OrderBookLevel]
    trade_records: List[TradeDetailRecord]
    trade_date: pd.Timestamp
    order_book_message: str = ''  # 默认为空
    trade_records_message: str = ''  # 默认为空
    is_index: bool = False  # 默认为个股（可交易）
    should_poll: bool = False  # 默认不轮询

    @classmethod
    def from_any(cls, data: Union['IntradayData', dict, Any]) -> Optional['IntradayData']:
        """
        从任意数据类型转换为 IntradayData 对象
        
        Args:
            data: 输入数据，可以是：
                - IntradayData 对象：直接返回
                - dict 字典：使用 **kwargs 构造
                - 其他类型：返回 None 并记录警告
        
        Returns:
            IntradayData 对象或 None（如果转换失败）
        
        示例：
            >>> data_dict = {'symbol': '000001.SH', 'name': '上证指数', ...}
            >>> intraday = IntradayData.from_any(data_dict)
            >>> 
            >>> intraday_obj = IntradayData(...)
            >>> same_obj = IntradayData.from_any(intraday_obj)  # 直接返回
        """
        if data is None:
            return None
        if isinstance(data, cls):
            # 已经是 IntradayData 对象，直接返回
            return data
        elif isinstance(data, dict):
            # 字典类型，尝试构造对象
            try:
                return cls(**data)
            except (TypeError, ValueError) as e:
                # 记录错误但不抛出异常
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"从字典构造 IntradayData 失败: {e}")
                return None
        else:
            # 不支持的类型
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"不支持的数据类型转换为 IntradayData: {type(data)}")
            return None


@dataclass
class TickRange:
    """
    Tick 数据时间范围
    
    属性：
        start_time: pd.Timestamp - 开始时间（包含）
        end_time: pd.Timestamp - 结束时间（包含）
        period_seconds: int - 时间粒度（秒），默认5秒
    
    示例：
        >>> # 获取 09:30 到 10:00 的分时数据，5秒粒度
        >>> tick_range = TickRange(
        ...     start_time=pd.Timestamp('2025-12-14 09:30:00'),
        ...     end_time=pd.Timestamp('2025-12-14 10:00:00'),
        ...     period_seconds=5
        ... )
    """
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    period_seconds: int = 5  # 默认5秒粒度

    def get_tick_count(self) -> int:
        """
        计算时间范围内的tick数量
        
        Returns:
            tick数量
        """
        total_seconds = int((self.end_time - self.start_time).total_seconds())
        return (total_seconds // self.period_seconds) + 1

    @classmethod
    def from_trading_phase(cls, trading_phase: 'TradingPhase', trade_date: pd.Timestamp,
                           current_time: Optional[pd.Timestamp] = None) -> 'TickRange':
        """
        根据交易时段创建 TickRange
        
        Args:
            trading_phase: 交易时段枚举
            trade_date: 交易日期
            current_time: 当前时间，如果为None则使用系统时间
        
        Returns:
            TickRange 对象
        """
        if current_time is None:
            current_time = pd.Timestamp.now()

        # 确保 trade_date 是 pd.Timestamp 类型
        if isinstance(trade_date, str):
            trade_date = pd.to_datetime(trade_date)

        # 提取日期部分并格式化为字符串用于构造时间
        trade_date_str = trade_date.strftime('%Y-%m-%d')

        if trading_phase.value == 'after_close':
            # 盘后：返回全天数据 09:30-15:00
            start_time = pd.Timestamp(f"{trade_date_str} 09:30:00")
            end_time = pd.Timestamp(f"{trade_date_str} 15:00:00")
        elif trading_phase.value == 'before_open':
            # 盘前：返回空范围
            start_time = pd.Timestamp(f"{trade_date_str} 09:30:00")
            end_time = start_time
        else:  # trading
            # 盘中：返回开盘至当前时间
            start_time = pd.Timestamp(f"{trade_date_str} 09:30:00")
            # 确保不超过当前时间和收盘时间
            end_time = min(
                current_time,
                pd.Timestamp(f"{trade_date_str} 15:00:00")
            )

        return cls(start_time=start_time, end_time=end_time, period_seconds=5)


class HistoricalDataProvider(ABC):
    """
    历史数据提供者接口（数据模块标准接口）
    
    设计目的：
    - 解耦业务逻辑与数据来源
    - 支持模拟数据（当前）和真实数据（未来）无缝切换
    - 为core/data模块集成预留标准接口
    
    数据标准：
    所有实现必须返回标准的OHLCV数据格式：
    - date: pd.Timestamp 类型，交易日期时间
    - open: float，开盘价
    - high: float，最高价
    - low: float，最低价
    - close: float，收盘价
    - volume: float，成交量
    
    注意事项：
    - 所有价格字段必须为float类型
    - 日期字段必须为pd.Timestamp类型
    - 成交量字段必须为float类型
    - 数据必须按日期升序排列
    - 不得包含缺失值（NaN）
    """

    @abstractmethod
    def get_index_prices(self, symbol: str,
                         start_date: pd.Timestamp,
                         end_date: pd.Timestamp,
                         market_local_time: pd.Timestamp,
                         period: str = 'daily') -> PriceData:
        """
        获取指数价格数据
        
        Args:
            symbol: 指数代码（如'000300.SH'沪深300）
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            market_local_time: 目标市场当前本地时间（不带时区信息）
            period: 周期
        Returns:
            PriceData: 包含标准OHLCV数据的结构化对象，具有明确的属性字段：
                - records: List[OHLCVRecord] - OHLCV数据记录列表
                - symbol: str - 指数代码
                - start_date: pd.Timestamp - 开始日期
                - end_date: pd.Timestamp - 结束日期
                - count: int - 记录数量
            
        数据标准：
        - date: pd.Timestamp 类型，交易日期
        - open: float，开盘价
        - high: float，最高价
        - low: float，最低价
        - close: float，收盘价
        - volume: float，成交量
            
        注意：所有实现必须返回完整的OHLCV数据，用于技术指标计算
        """
        pass

    @abstractmethod
    def get_index_returns(self, symbol: str,
                          start_date: pd.Timestamp,
                          end_date: pd.Timestamp) -> pd.Series:
        """
        获取指数收益率序列
        
        Args:
            symbol: 指数代码
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            Series with date index and return values
        """
        pass

    @abstractmethod
    def get_stock_prices(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp,
                         market_local_time: pd.Timestamp, period: str = 'daily') -> PriceData:
        """
        获取个股历史价格数据

        Args:
            symbol: 股票代码（支持市场后缀，如 '000001.SZ'）
            start_date: 开始日期
            end_date: 结束日期
            market_local_time: 目标市场当前本地时间（不带时区信息）
            period: 周期
        
        Returns:
            PriceData: 包含标准OHLCV数据的结构化对象，具有明确的属性字段：
                - records: List[OHLCVRecord] - OHLCV数据记录列表
                - symbol: str - 股票代码
                - start_date: pd.Timestamp - 开始日期
                - end_date: pd.Timestamp - 结束日期
                - count: int - 记录数量
            
        数据标准：与 get_index_prices 相同
        """
        pass

    def get_realtime_kline(self, symbol, period, provider):
        """
        获取实时K线数据（指数）

        Args:
            symbol: 指数代码
            period: K线周期
            provider: 数据提供者实例

        Returns:
            DataFrame: 包含实时K线数据，列包括：
                - date: pd.Timestamp 类型，交易日期时间
                - open: float，开盘价
                - high: float，最高价
                - low: float，最低价
                - close: float，收盘价
                - volume: float，成交量
        """
        pass

    @abstractmethod
    def get_intraday_data(self, symbol: str, tick_range: TickRange = None,
                          market_local_time: pd.Timestamp = None) -> IntradayData:
        """
        获取分时图数据（1分钟级别）
        
        Args:
            symbol: 证券代码（如'000001.SH'上证指数）
            tick_range: 时间范围
            market_local_time: 目标市场当前本地时间（不带时区信息）
        
        Returns:
            IntradayData: 包含完整分时数据的结构化对象：
                - symbol: 证券代码
                - name: 证券名称
                - current_price: 当前价格
                - yesterday_close: 昨收价
                - change: 涨跌额
                - change_percent: 涨跌幅（%）
                - ticks: List[IntradayTickRecord] - 分时tick数据
                - order_book_bids: List[OrderBookLevel] - 买盘10档
                - order_book_asks: List[OrderBookLevel] - 卖盘10档
                - trade_records: List[TradeDetailRecord] - 成交明细（最近20笔）
                - trade_date: 交易日期
        
        数据标准：
        - ticks: 按时间升序排列，覆盖交易时段（09:30-11:30, 13:00-15:00）
        - order_book: 买盘从高到低，卖盘从低到高
        - trade_records: 按时间降序排列（最新的在前）
        
        注意：实现类可以返回实时数据或历史分时数据
        """
        pass
    
    @abstractmethod
    def get_all_symbols(self, market: 'MarketCode') -> pd.DataFrame:
        """
        获取指定市场的所有股票代码列表
        
        Args:
            market: 市场枚举（MarketCode.CN, MarketCode.US, MarketCode.HK等）
        
        Returns:
            pd.DataFrame: 股票列表，包含以下列：
                - symbol: 股票代码（带市场后缀，如 '000001.SZ'）
                - name: 股票名称
                - markets: 市场代码
                
        示例：
            >>> provider = AKShareDataProvider()
            >>> df = provider.get_all_symbols(MarketCode.CN)
            >>> df.head()
               symbol      name markets
            0  000001.SZ  平安银行     CN
            1  000002.SZ   万科A      CN
        """
        pass
    
    @abstractmethod
    def get_complete_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取指定股票的完整基本面数据
        
        Args:
            symbol: 股票代码（带市场后缀，如 '000001.SZ'）
        
        Returns:
            Dict[str, Any]: 完整的基本面数据字典，包含：
                - 估值指标：pb, pe, ps, pcf
                - 盈利能力：roe, roic, gross_margin
                - 成长性：revenue_growth, profit_growth, ocf_growth
                - 资产质量：资产负债率, 流动比率, 商誉占比, 应收账款占比
                - 流动性：market_cap, avg_volume
                - 基本信息：name, sector, industry, markets
                
        示例：
            >>> provider = AKShareDataProvider()
            >>> data = provider.get_complete_fundamental_data('000001.SZ')
            >>> print(data['pe'])
            5.2
            >>> print(data['roe'])
            0.15
        
        注意：
        - 所有财务数据应为最新年报或TTM数据
        - 增长率应使用同比数据
        - 百分比字段使用小数表示（如15%表示为0.15）
        """
        pass
