"""
数据提供者配置管理器

职责：管理 data_provider.yml 的加载和查询
定位：业务基础共享
"""

import logging
import os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class DataProviderConfig:
    """数据提供者配置管理器

    从 config/{env}/data_provider.yml 读取数据源配置，
    提供数据源查询、市场映射等功能。
    """

    def __init__(self, config_dir: str):
        """
        初始化数据提供者配置管理器

        Args:
            config_dir: 配置文件目录路径（如 config/dev）
        """
        self._config_dir = config_dir
        self._config = self._load_yaml_config('data_provider.yml')

        # 解析顶层字段
        self.default_index = self._config.get('default_index', '000300.SH')
        self.cache_enabled = self._config.get('cache_enabled', True)
        self.cache_ttl = self._config.get('cache_ttl', 3600)
        self.max_retries = self._config.get('max_retries', 3)

        # 解析 providers 列表
        self.providers = self._config.get('providers', [])
        if not isinstance(self.providers, list):
            logger.warning("providers 配置不是列表，使用空列表")
            self.providers = []

    def _load_yaml_config(self, filename: str) -> Dict[str, Any]:
        """加载 YAML 配置文件"""
        try:
            config_path = os.path.join(self._config_dir, filename)

            if not os.path.exists(config_path):
                logger.warning(f"未找到配置文件: {config_path}，使用空配置")
                return {}

            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            logger.info(f"✅ {filename} 加载成功")
            return config

        except Exception as e:
            logger.error(f"加载 {filename} 失败: {e}")
            return {}

    def get_providers(self) -> List[Dict[str, Any]]:
        """获取所有数据提供者配置列表"""
        return self.providers

    def get_provider_by_id(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取数据提供者配置

        Args:
            provider_id: 提供者 ID（如 'akshare', 'yahoo', 'tushare'）

        Returns:
            提供者配置字典，未找到返回 None
        """
        for provider in self.providers:
            if provider.get('id') == provider_id:
                return provider
        return None

    def get_provider_for_market(self, market_code: str) -> Optional[str]:
        """根据市场代码获取默认数据提供者 ID

        按 providers 列表中的顺序，返回第一个支持该市场的提供者。

        Args:
            market_code: 市场代码（如 'CN', 'US', 'HK'）

        Returns:
            提供者 ID，未找到返回 None
        """
        for provider in self.providers:
            markets = provider.get('markets', [])
            if market_code in markets:
                return provider.get('id')

        logger.warning(f"未找到支持市场 {market_code} 的数据源配置")
        return None

    def get_provider_proxy_config(self, provider_id: str) -> bool:
        """获取指定数据源的代理配置

        Args:
            provider_id: 数据源 ID

        Returns:
            bool: 是否使用代理
        """
        provider = self.get_provider_by_id(provider_id)
        if provider:
            return provider.get('use_proxy', False)
        return False

    def get_default_index(self) -> str:
        """获取默认指数代码"""
        return self.default_index

    def reload(self):
        """重新加载数据提供者配置"""
        self.__init__(self._config_dir)
