"""
缓存基础设施 - 三层缓存管理

三层数据获取策略:
1. 内存缓存（Memory）- 毫秒级，永不过期（股票历史不会变）
2. 数据库缓存（Database）- 0.1-0.3秒，持久化存储
3. 外部API（External API）- 4-8秒，原始数据源

核心特性:
- 按时间窗口粒度缓存（最小粒度为周）
- 逐窗口多层查询，精细化缓存利用
- 自动回写机制，新数据写入各层缓存
- 对外透明: 调用者无需关心数据来源和缓存层级

对外接口：
- ThreeLayerCacheManager：三层缓存管理器
- create_cache_manager()：工厂方法，自动加载配置并创建管理器
"""

import logging
from typing import Dict, Any

import pandas as pd

logger = logging.getLogger('Cache')

# 导出核心类
from .manager import ThreeLayerCacheManager
from .window_cache import WindowsCache


def _load_cache_config() -> Dict[str, Any]:
    """
    加载缓存配置（从 database.yml 读取）
    
    Returns:
        Dict: 缓存配置字典
    """
    # 默认配置
    default_config = {
        'cache_mode': 'memory',
        'window_size': 1,
        'memory_max_windows': 1000,
        'db_enabled': True,
    }
    
    try:
        from core.share.config_manager import ConfigManager
        config_manager = ConfigManager()
        
        # 从 database.yml 读取配置
        if hasattr(config_manager, 'config'):
            db_config = config_manager.config.get('database', {})
            if db_config:
                cache_strategy = db_config.get('cache_strategy', {})
                
                # 读取缓存模式和各层配置
                cache_mode = cache_strategy.get('cache_mode', 'memory')
                window_size = cache_strategy.get('window_size', 1)
                memory_config = cache_strategy.get('memory', {})
                db_cache_config = cache_strategy.get('database', {})

                return {
                    'cache_mode': cache_mode,
                    'window_size': window_size,
                    'memory_max_windows': memory_config.get('max_windows', 1000),
                    'db_enabled': db_cache_config.get('enabled', True),
                }
    except Exception as e:
        logger.debug(f"加载缓存配置失败，使用默认值: {e}")
    
    return default_config


def create_cache_manager() -> ThreeLayerCacheManager:
    """
    工厂方法：创建三层缓存管理器

    自动从 database.yml 加载配置，创建并返回 ThreeLayerCacheManager 实例。

    Returns:
        ThreeLayerCacheManager: 三层缓存管理器实例

    Example:
import pandas as pd        >>> from infrastructure.cache import create_cache_manager
        >>> cache_manager = create_cache_manager()
        >>> # 使用缓存管理器
        >>> data = cache_manager.get_data(
        ...     symbol='000300.SH',
        ...     from_date=pd.Timestamp('2025-01-01'),
        ...     to_date=pd.Timestamp('2025-01-31'),
        ...     period='weekly',
        ...     api_fetch_func=my_api_func
        ... )
    """
    # 加载配置
    config = _load_cache_config()

    # 创建管理器
    cache_manager = ThreeLayerCacheManager(
        db_service=None,
    )

    logger.debug(f"✅ 缓存管理器已创建: cache_mode={config['cache_mode']}")
    return cache_manager


__all__ = [
    'ThreeLayerCacheManager',
    'WindowsCache',
    'create_cache_manager',
]
