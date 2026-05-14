"""
数据源选择服务（领域层）

职责：
- 根据市场/symbol 选择合适的数据源
- 封装数据源选择的领域逻辑
- 与配置系统集成，支持动态配置

设计原则：
- 领域逻辑下沉：数据源选择是领域内在知识，不属于应用层
- 配置驱动：通过 market_sources 配置决定映射关系
- 可复用：可被多个应用层场景使用（API、回测、分析等）
"""

from typing import TYPE_CHECKING
import logging

from core.share.market import MarketUtils, MarketCode
from core.share.config_manager import ConfigManager

if TYPE_CHECKING:
    from core.data.providers.protocols import HistoricalDataProvider

logger = logging.getLogger('ProviderSelector')


class ProviderSelector:
    """数据源选择服务
    
    根据 symbol/markets 选择合适的数据提供者
    """
    
    def __init__(self, config_manager: ConfigManager = None):
        """初始化数据源选择器
        
        Args:
            config_manager: 配置管理器（可选，默认创建新实例）
        """
        self.config_manager = config_manager or ConfigManager()
    
    def select_provider_for_symbol(self, symbol: str, provider_factory) -> 'HistoricalDataProvider':
        """根据 symbol 选择数据提供者
        
        Args:
            symbol: 股票/指数代码（如 '000300.SH', '^GSPC'）
            provider_factory: 数据提供者工厂实例
        
        Returns:
            HistoricalDataProvider: 选中的数据提供者实例
        
        Examples:
            >>> selector = ProviderSelector()
            >>> from core.data.providers.factory import get_global_factory
            >>> factory = get_global_factory()
            >>> provider = selector.select_provider_for_symbol('000300.SH', factory)
            >>> # provider 将是 akshare（根据配置文件 market_sources）
        
        逻辑流程:
            1. 使用 MarketUtils 推断市场类型
            2. 从配置文件读取 market_sources 映射
            3. 选择对应的 provider_id
            4. 从 factory 获取 provider 实例
        """
        # 1. 推断市场
        market_code = MarketUtils.infer_market_from_symbol(symbol)
        logger.debug(f"根据 symbol='{symbol}' 推断市场: {market_code.value}")
        
        # 2. 获取 provider_id
        provider_id = self.get_provider_id_for_market(market_code)
        logger.info(f"为市场 '{market_code.value}' 选择 provider: {provider_id}")
        
        # 3. 从 factory 获取实例
        provider = provider_factory.get(provider_id)
        return provider
    
    def get_provider_id_for_market(self, market: MarketCode) -> str:
        """根据市场代码获取数据源 ID
        
        Args:
            market: 市场枚举（MarketCode.CN, MarketCode.US 等）
        
        Returns:
            str: 数据源 ID（如 'akshare', 'yahoo'）
        
        Examples:
            >>> selector = ProviderSelector()
            >>> selector.get_provider_id_for_market(MarketCode.CN)
            'akshare'
            >>> selector.get_provider_id_for_market(MarketCode.US)
            'yahoo'
        
        配置来源:
            从 config/dev/data_provider.yml 的 market_sources 字段读取
        """
        # 从配置文件获取 market_sources 映射
        data_config = self.config_manager.get_market_config()
        market_sources = data_config.market_sources or {}
        
        # 查找对应的 provider_id
        market_str = market.value if isinstance(market, MarketCode) else str(market)
        provider_id = market_sources.get(market_str)
        
        if not provider_id:
            logger.warning(f"市场 '{market_str}' 在 market_sources 中未配置，使用默认 'akshare'")
            provider_id = 'akshare'
        
        return provider_id
    
    def select_provider_for_market(self, market: MarketCode, provider_factory) -> 'HistoricalDataProvider':
        """根据市场枚举选择数据提供者
        
        Args:
            market: 市场枚举（MarketCode.CN, MarketCode.US 等）
            provider_factory: 数据提供者工厂实例
        
        Returns:
            HistoricalDataProvider: 选中的数据提供者实例
        
        Examples:
            >>> selector = ProviderSelector()
            >>> from core.data.providers.factory import get_global_factory
            >>> factory = get_global_factory()
            >>> provider = selector.select_provider_for_market(MarketCode.CN, factory)
        """
        provider_id = self.get_provider_id_for_market(market)
        logger.info(f"为市场 '{market.value}' 选择 provider: {provider_id}")
        
        provider = provider_factory.get(provider_id)
        return provider
    
    def get_market_sources_mapping(self) -> dict:
        """获取完整的市场数据源映射配置
        
        Returns:
            dict: 市场到数据源的映射字典
        
        Examples:
            >>> selector = ProviderSelector()
            >>> mapping = selector.get_market_sources_mapping()
            >>> mapping
            {'CN': 'akshare', 'US': 'yahoo', 'HK': 'akshare', ...}
        """
        market_config = self.config_manager.get_market_config()
        return market_config.market_sources or {}
