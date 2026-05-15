"""历史K线数据获取体系

提供统一的历史数据获取接口，支持内存缓存、数据库、外部API三层回退。
"""

from .interface import IDataProvider, ICompositeProvider
from .memory_provider import MemoryCacheProvider
from .db_provider import DbProvider
from .external_provider import ExternalApiProvider
from .multi_source import MultiSourceProvider
from .three_layer import ThreeLayerProvider
from .adapter import HistoryProviderAdapter

__all__ = [
    'IDataProvider',
    'ICompositeProvider',
    'MemoryCacheProvider',
    'DbProvider',
    'ExternalApiProvider',
    'MultiSourceProvider',
    'ThreeLayerProvider',
    'HistoryProviderAdapter',
]
