"""
数据提供者工厂 - 统一创建和管理所有数据源

职责：
- 注册和管理所有内置数据提供者
- 支持外部注入自定义数据提供者（依赖注入）
- 提供统一的创建接口
- 确保所有provider实现HistoricalDataProvider接口

设计原则：
- 工厂模式：集中管理provider创建逻辑
- 依赖注入：支持外部注入自定义实现（测试Mock等）
- 类型安全：所有provider必须实现统一接口
- 懒加载：按需创建provider实例

使用示例：
    # 基本使用
    factory = DataProviderFactory()
    provider = factory.create('yahoo')
    data = provider.get_index_prices('000300.SH', '2020-01-01', '2020-12-31', pd.Timestamp.now())
    
    # 注入自定义provider
    factory.register('custom', MyCustomProvider)
    provider = factory.create('custom', **config)
"""

from typing import Dict, Type, Any, Optional
import logging

logger = logging.getLogger('DataProviderFactory')


class DataProviderFactory:
    """
    数据提供者工厂
    
    功能：
    - 注册内置数据提供者（yahoo, tushare, mock等）
    - 支持外部注入自定义provider（依赖注入）
    - 统一创建provider实例
    - 类型验证和错误处理
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化工厂，从配置加载 providers
        
        Args:
            config: 配置字典，包含 providers 列表。如果为 None，则从默认配置路径加载
        """
        self._instances: Dict[str, Any] = {}  # 存储单例实例
        self._config = config or self._load_default_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """
        加载默认配置（从 config/dev/data_provider.yml）
        
        Returns:
            Dict: 配置字典
        """
        # 使用 ConfigManager 获取配置（封装环境逻辑）
        from core.share.config_manager import ConfigManager
        config_manager = ConfigManager()
        config = config_manager.get('data_provider', {})
        
        if config:
            logger.info(f"✅ 从 ConfigManager 加载配置")
            logger.info(f"✅ 加载了 {len(config.get('providers', []))} 个providers")
            return config
        else:
            logger.error("配置加载失败，返回空配置")
            return {'providers': []}
    
    def _get_provider_class(self, name: str) -> Type:
        """
        从配置文件动态加载 provider 类
        
        Args:
            name: provider名称
        
        Returns:
            Provider 类
        
        Raises:
            ValueError: provider 不存在或加载失败
        """
        # 从配置列表中查找该 provider
        providers_config = self._config.get('providers', [])
        for provider_config in providers_config:
            if provider_config.get('id') == name:
                adapter_module = provider_config.get('adapter_module')
                adapter_class = provider_config.get('adapter_class')
                
                if not adapter_module or not adapter_class:
                    raise ValueError(f"Provider '{name}' 配置不完整：缺少 adapter_module 或 adapter_class")
                
                try:
                    # 动态导入模块
                    module = __import__(adapter_module, fromlist=[adapter_class])
                    return getattr(module, adapter_class)
                except Exception as e:
                    raise ValueError(f"加载 provider '{name}' 失败: {e}")
        
        # 如果配置中没有找到
        available = [p.get('id') for p in providers_config if p.get('id')]
        raise ValueError(
            f"未知的provider: '{name}'\n"
            f"可用的providers: {available}\n"
            f"提示: 请在配置文件中添加 provider 配置"
        )
    
    def _get_provider_config(self, name: str) -> Dict[str, Any]:
        """
        从配置文件获取 provider 的初始化参数
        
        Args:
            name: provider名称
        
        Returns:
            Dict: provider的初始化参数
        """
        # 从配置列表中查找该 provider 的配置
        providers_config = self._config.get('providers', [])
        for provider_config in providers_config:
            if provider_config.get('id') == name:
                # 提取初始化参数（排除元数据字段和业务配置字段）
                excluded_fields = {
                    'id', 'name', 'type', 'description', 'status',
                    'adapter_module', 'adapter_class', 'markets',
                    'requires_auth', 'auth_type', 'rate_limit',
                    'features', 'installation', 'registration', 'last_test',
                    'supports_period',  # 🔧 数据源特性，不传给构造函数
                    'use_proxy'  # 🔧 代理配置已在各 Provider 内部通过 ConfigManager 读取
                }
                
                kwargs = {k: v for k, v in provider_config.items() if k not in excluded_fields}
                return kwargs
        
        # 如果配置中没有找到，返回空字典（使用默认参数）
        return {}
    
    def _create(self, name: str) -> Any:
        """
        创建数据提供者实例（私有方法，每次都创建新实例）
        
        Args:
            name: provider名称
        
        Returns:
            HistoricalDataProvider实例
        
        Raises:
            ValueError: provider不存在
        
        Note:
            这是私有方法，外部应使用 get() 方法获取单例
            创建参数从配置文件中自动读取
        """
        # 从配置动态加载 provider 类
        provider_class = self._get_provider_class(name)
        
        # 从配置文件获取该 provider 的初始化参数
        kwargs = self._get_provider_config(name)
        
        try:
            instance = provider_class(**kwargs)
            logger.debug(f"创建provider实例: {name} ({provider_class.__name__})")
            return instance
        except Exception as e:
            logger.error(f"创建provider失败: {name} - {e}")
            raise RuntimeError(f"Failed to create provider '{name}': {e}") from e
    

    def get(self, name: str) -> Any:
        """
        获取数据提供者单例实例
        
        如果实例已存在则返回现有实例，否则调用 _create() 创建新实例并缓存
        
        Args:
            name: provider名称
        
        Returns:
            HistoricalDataProvider单例实例
        
        Raises:
            ValueError: provider不存在
        
        Example:
            >>> factory = DataProviderFactory()
            >>> provider1 = factory.get('real')
            >>> provider2 = factory.get('real')
            >>> assert provider1 is provider2  # 同一个实例
        
        Note:
            - 推荐在应用程序中使用此方法获取provider实例
            - 单例由 get() 方法内部调用 _create() 确保只创建一次
            - 创建参数从配置文件中自动读取
        """
        # 如果单例已存在，直接返回
        if name in self._instances:
            logger.debug(f"返回已存在的单例: {name}")
            return self._instances[name]
        
        # 调用 _create() 创建新实例
        instance = self._create(name)
        
        # 缓存单例实例
        self._instances[name] = instance
        logger.debug(f"缓存单例: {name}")
        
        return instance
    
    def list_providers(self) -> list:
        """
        列出所有已配置的provider名称
        
        Returns:
            provider名称列表
        """
        providers = [p.get('id') for p in self._config.get('providers', []) if p.get('id')]
        return providers
    
    def is_registered(self, name: str) -> bool:
        """
        检查provider是否已配置
        
        Args:
            name: provider名称
        
        Returns:
            是否已配置
        """
        providers_config = self._config.get('providers', [])
        return any(p.get('id') == name for p in providers_config)
    



# 全局单例工厂（可选）
_global_factory: Optional[DataProviderFactory] = None


def get_global_factory() -> DataProviderFactory:
    """
    获取全局单例工厂
    
    Returns:
        全局DataProviderFactory实例
    
    Example:
        >>> factory = get_global_factory()
        >>> provider = factory.get('yahoo')
    """
    global _global_factory
    if _global_factory is None:
        _global_factory = DataProviderFactory()
    return _global_factory


def reset_global_factory():
    """
    重置全局工厂（主要用于测试）
    """
    global _global_factory
    _global_factory = None
