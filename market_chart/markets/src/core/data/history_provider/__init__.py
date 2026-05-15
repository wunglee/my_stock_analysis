"""历史K线数据获取体系

提供统一的历史数据获取接口，支持内存缓存、数据库、外部API三层回退。
"""

from .interface import IDataProvider, ICompositeProvider

__all__ = ['IDataProvider', 'ICompositeProvider']
