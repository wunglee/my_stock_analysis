"""
数据库缓存层 - 窗口级别的数据库缓存

职责：
1. 按窗口粒度缓存数据到数据库
2. 从数据库查询窗口数据
3. 与 BaseDataProvider 的数据库服务集成
"""

import logging
from typing import Optional
import pandas as pd

logger = logging.getLogger('DBCache')


class DBCache:
    """数据库缓存层"""
    
    def __init__(self, db_service=None):
        """
        初始化数据库缓存
        
        Args:
            db_service: 数据库服务实例
        """
        self._db_service = db_service
        
        if db_service is None:
            logger.warning("⚠️ 数据库服务未配置，DB缓存层不可用")
        else:
            logger.info("✅ DBCache 初始化完成")
    
    def get(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp) -> Optional[pd.DataFrame]:
        """
        从数据库获取数据
        
        Args:
            symbol: 股票/指数代码
            start_date: 开始日期（pd.Timestamp）
            end_date: 结束日期（pd.Timestamp）
        
        Returns:
            DataFrame 或 None
        """
        if self._db_service is None:
            return None
        
        try:
            # 调用数据库服务查询
            df = self._db_service.get_cached_data(symbol, start_date, end_date)
            
            if df is not None and not df.empty:
                logger.debug(f"✅ 数据库命中: {symbol} {start_date}~{end_date} ({len(df)} 条)")
                return df
        except Exception as e:
            logger.warning(f"⚠️ 数据库读取失败: {symbol}, error={e}")
        
        return None
    
    def set(self, symbol: str, data: pd.DataFrame) -> None:
        """
        写入数据到数据库
        
        Args:
            symbol: 股票/指数代码
            data: 数据
        """
        if self._db_service is None or data is None or data.empty:
            return
        
        try:
            # 调用数据库服务写入
            self._db_service.cache_data(symbol, data)
            logger.debug(f"✅ 数据库写入: {symbol} ({len(data)} 条)")
        except Exception as e:
            logger.warning(f"⚠️ 数据库写入失败: {symbol}, error={e}")
