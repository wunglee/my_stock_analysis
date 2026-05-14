"""
数据库配置管理器

职责：管理 database.yml 的加载和查询
定位：业务基础共享
"""

import logging
import os
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """数据库配置管理器

    从 config/{env}/database.yml 读取数据库配置，
    提供数据库连接参数、同步配置、性能监控等查询接口。
    """

    def __init__(self, config_dir: str):
        """
        初始化数据库配置管理器

        Args:
            config_dir: 配置文件目录路径（如 config/dev）
        """
        self._config_dir = config_dir
        self._config = self._load_yaml_config('database.yml')

        # 解析数据库类型
        self.database_type = self._config.get('database_type', 'sqlite')

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

    def get_database_type(self) -> str:
        """获取当前使用的数据库类型"""
        return self.database_type

    def get_connection_config(self) -> Dict[str, Any]:
        """获取当前数据库类型的连接配置

        Returns:
            对应数据库类型的连接参数字典
        """
        return self._config.get(self.database_type, {})

    def get_sqlite_config(self) -> Dict[str, Any]:
        """获取 SQLite 配置"""
        return self._config.get('sqlite', {})

    def get_postgresql_config(self) -> Dict[str, Any]:
        """获取 PostgreSQL 配置"""
        return self._config.get('postgresql', {})

    def get_mysql_config(self) -> Dict[str, Any]:
        """获取 MySQL 配置"""
        return self._config.get('mysql', {})

    def get_sync_config(self) -> Dict[str, Any]:
        """获取数据同步配置"""
        return self._config.get('sync', {})

    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取性能监控配置"""
        return self._config.get('monitoring', {})

    def get_database_path(self) -> str:
        """获取 SQLite 数据库文件路径（仅 SQLite 适用）"""
        sqlite_config = self.get_sqlite_config()
        return sqlite_config.get('database_path', 'data/market_data.db')

    def reload(self):
        """重新加载数据库配置"""
        self.__init__(self._config_dir)
