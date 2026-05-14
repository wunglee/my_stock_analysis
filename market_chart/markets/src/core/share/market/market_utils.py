"""
市场工具类（领域层共享）

职责：
- 提供市场识别、推断等基础功能
- 支持从 symbol/symbol 推断市场类型
- 可被所有层（应用层、领域层）复用
"""

import logging
from typing import Optional

import pandas as pd

from core.share.market.data_types import OHLCVRecord
from core.share.market.market_enums import MarketCode


logger = logging.getLogger(__name__)


class MarketUtils:
    """市场工具类
    
    提供市场相关的通用工具方法
    """

    @staticmethod
    def infer_market_from_symbol(symbol: str) -> MarketCode:
        """从股票/指数代码推断市场类型
        
        Args:
            symbol: 股票/指数代码（如 '000300.SH', '^GSPC.US', 'HSI'）
        
        Returns:
            MarketCode: 推断出的市场代码枚举
        
        Examples:
            >>> MarketUtils.infer_market_from_symbol('000300.SH')
            <MarketCode.CN: 'CN'>
            >>> MarketUtils.infer_market_from_symbol('^GSPC.US')
            <MarketCode.US: 'US'>
            >>> MarketUtils.infer_market_from_symbol('HSI.HK')
            <MarketCode.HK: 'HK'>
            >>> MarketUtils.infer_market_from_symbol('0700.HK')
            <MarketCode.HK: 'HK'>
        
        规则：
            - A股市场：.SH（上海）、.SZ（深圳）、.CN
            - 港股市场：.HK、.HKG、HSI（恒生指数）
            - 美股市场：.US（如 ^GSPC.US、^DJI.US、^IXIC.US）
            - 日本市场：.JP
            - 欧洲市场：.EU
            - 新加坡：.SG
            - 默认：MarketCode.CN
        """
        if not symbol:
            return MarketCode.CN

        symbol_upper = symbol.upper()

        # A股市场（上海/深圳）
        if any(symbol_upper.endswith(suffix) for suffix in ['.SH', '.SZ', '.CN']):
            return MarketCode.CN

        # 港股市场
        if any(symbol_upper.endswith(suffix) for suffix in ['.HK', '.HKG']) or symbol_upper == 'HSI':
            return MarketCode.HK

        # 日本市场
        if symbol_upper.endswith('.JP'):
            return MarketCode.JP

        # 欧洲市场
        if symbol_upper.endswith('.EU'):
            return MarketCode.EU

        # 新加坡市场
        if symbol_upper.endswith('.SG'):
            return MarketCode.SG

        # 美股市场（.US 后缀）
        if symbol_upper.endswith('.US'):
            return MarketCode.US

        # 默认为 A股市场
        return MarketCode.CN

    @staticmethod
    def infer_market_from_metadata(metadata: dict) -> Optional[MarketCode]:
        """从元数据中提取市场类型
        
        Args:
            metadata: 元数据字典（可能包含 'market_type' 或 'markets' 字段）
        
        Returns:
            MarketCode: 提取出的市场代码枚举，如果无法提取则返回 None
        
        Examples:
            >>> MarketUtils.infer_market_from_metadata({'market_type': 'CN'})
            <MarketCode.CN: 'CN'>
            >>> MarketUtils.infer_market_from_metadata({'markets': MarketCode.US})
            <MarketCode.US: 'US'>
            >>> MarketUtils.infer_market_from_metadata({'tmp': 'data'})
            None
        """
        if not metadata:
            return None

        # 尝试从 market_type 字段提取
        market_type = metadata.get('market_type')
        if market_type:
            if isinstance(market_type, MarketCode):
                return market_type
            if isinstance(market_type, str) and MarketCode.is_valid(market_type.upper()):
                return MarketCode(market_type.upper())

        # 尝试从 markets 字段提取
        market = metadata.get('markets')
        if market:
            if isinstance(market, MarketCode):
                return market
            if isinstance(market, str) and MarketCode.is_valid(market.upper()):
                return MarketCode(market.upper())

        return None

    @staticmethod
    def detect_market_with_fallback(symbol: str = None, metadata: dict = None) -> MarketCode:
        """综合检测市场类型（优先元数据，其次 symbol 启发式）
        
        Args:
            symbol: 股票/指数代码
            metadata: 元数据字典
        
        Returns:
            MarketCode: 检测出的市场代码枚举
        
        Examples:
            >>> # 优先使用元数据
            >>> MarketUtils.detect_market_with_fallback(
            ...     symbol='000300.SH',
            ...     metadata={'market_type': 'US'}
            ... )
            <MarketCode.US: 'US'>
            
            >>> # 元数据缺失时使用 symbol
            >>> MarketUtils.detect_market_with_fallback(symbol='000300.SH')
            <MarketCode.CN: 'CN'>
            
            >>> # 都缺失时返回默认值
            >>> MarketUtils.detect_market_with_fallback()
            <MarketCode.CN: 'CN'>
        """
        # 1. 优先使用元数据
        if metadata:
            market = MarketUtils.infer_market_from_metadata(metadata)
            if market:
                return market

        # 2. 其次使用 symbol 启发式推断
        if symbol:
            return MarketUtils.infer_market_from_symbol(symbol)

        # 3. 默认为 A股市场
        return MarketCode.CN

    @staticmethod
    def standardize_format(df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
        """
        标准化指数数据格式（处理不同API的列名差异）
        
        Args:
            df: 原始DataFrame
            symbol: 证券代码（用于处理MultiIndex列名）
        
        Returns:
            标准化的DataFrame with columns: ['date', 'open', 'high', 'low', 'close', 'volume']
            
        数据标准：
        - date: pd.Timestamp 类型，交易日期时间
        - open: float，开盘价
        - high: float，最高价
        - low: float，最低价
        - close: float，收盘价
        - volume: float，成交量
        """
        # 🔧 处理不同 API 返回的列名差异
        # A股: date, open, close, high, low, volume, amount
        # 港股/美股: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额

        date_col = None
        if isinstance(df.columns, pd.Index) and df.index.name:
            date_col=df.index.name
        close_col = None
        high_col = None
        low_col = None
        open_col = None
        volume_col = None

        # 尝试识别日期列
        if not date_col:
            for col in ['日期', 'date', 'Date', 'DATE']:
                if col in df.columns:
                    date_col = col
                    break

        # 尝试识别开盘价列
        if not open_col:
            for col in ['开盘', 'open', 'Open', 'OPEN']:
                if col in df.columns:
                    open_col = col
                    break

        # 尝试识别最高价列
        if not high_col:
            for col in ['最高', 'high', 'High', 'HIGH']:
                if col in df.columns:
                    high_col = col
                    break

        # 尝试识别最低价列
        if not low_col:
            for col in ['最低', 'low', 'Low', 'LOW']:
                if col in df.columns:
                    low_col = col
                    break

        # 尝试识别收盘价列
        if not close_col:
            for col in ['收盘', 'close', 'Close', 'CLOSE', '收盘价']:
                if col in df.columns:
                    close_col = col
                    break

        # 尝试识别成交量列
        if not volume_col:
            for col in ['成交量', 'volume', 'Volume', 'VOLUME']:
                if col in df.columns:
                    volume_col = col
                    break

        if not date_col or not close_col:
            raise ValueError(f"Cannot find date or close columns in DataFrame. Columns: {df.columns.tolist()}")

        # 如果缺少OHLC数据，使用收盘价填充
        if isinstance(df.index, pd.DatetimeIndex):
            dates = df.index
        else:
            dates = pd.to_datetime(df[date_col])
        if hasattr(dates, 'tz') and dates.tz is not None:
            dates = dates.tz_localize(None)

        standardized = pd.DataFrame({
            'date': dates,
            'open': df[open_col].astype(float) if open_col in df.columns else df[close_col].astype(float),
            'high': df[high_col].astype(float) if high_col in df.columns else df[close_col].astype(float),
            'low': df[low_col].astype(float) if low_col in df.columns else df[close_col].astype(float),
            'close': df[close_col].astype(float),
            'volume': df[volume_col].astype(float) if volume_col in df.columns else 0.0
        })

        # 按日期排序
        standardized = standardized.sort_values('date').reset_index(drop=True)

        # 数据清洗：移除NaN和异常值
        original_len = len(standardized)
        standardized = standardized.dropna(subset=['close'])
        if len(standardized) < original_len:
            logger.warning(f"Removed {original_len - len(standardized)} rows with missing close prices")

        return standardized

    @staticmethod
    def standardize_format_to_price_data(df: pd.DataFrame, symbol: str = "") -> 'PriceData':
        """
        标准化数据格式并转换为PriceData对象
        
        Args:
            df: 原始DataFrame
            symbol: 证券代码
        
        Returns:
            PriceData: 标准化后的数据对象
        """
        # 局部导入避免循环依赖
        from core.data.providers.protocols import PriceData
        from core.share.market.market_time_utils import MarketTimeUtils
        if df is None or df.empty:
            # 空数据返回空的PriceData
            return PriceData(
                symbol=symbol,
                records=[],
                start_date=MarketTimeUtils.get_market_time_now(symbol),
                end_date=MarketTimeUtils.get_market_time_now(symbol),
                count=0
            )

        # 标准化格式
        standardized_df = MarketUtils.standardize_format(df, symbol)

        # 转换为OHLCVRecord列表
        records = []
        for _, row in standardized_df.iterrows():
            try:
                record = OHLCVRecord(
                    date=pd.to_datetime(row['date']),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume'])
                )
                records.append(record)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid row for {symbol}: {e}")
                continue

        # 计算start_date和end_date
        start_date = records[0].date if records else MarketTimeUtils.get_market_time_now(symbol)
        end_date = records[-1].date if records else MarketTimeUtils.get_market_time_now(symbol)

        return PriceData(
            symbol=symbol,
            records=records,
            start_date=start_date,
            end_date=end_date,
            count=len(records)
        )


    @staticmethod
    def is_index(symbol: str) -> bool:
        return symbol.startswith('^')
