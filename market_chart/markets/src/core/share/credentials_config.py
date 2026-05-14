"""
凭证配置管理器

职责：管理 credentials.yml 的加载、读取和持久化
定位：业务基础共享
"""

import logging
import os
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)


class CredentialsConfig:
    """凭证配置管理器

    从 config/{env}/credentials.yml 读取凭证配置，
    支持点号分隔路径查询和持久化更新。
    """

    def __init__(self, config_dir: str):
        """
        初始化凭证配置管理器

        Args:
            config_dir: 配置文件目录路径（如 config/dev）
        """
        self._config_dir = config_dir
        self._credentials = self._load_yaml_config('credentials.yml')

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

    def get(self, key: str, default: Any = None) -> Any:
        """获取凭证值

        Args:
            key: 配置键，支持点号分隔的嵌套路径（如 'tushare.token'）
            default: 默认值

        Returns:
            配置值或默认值
        """
        if not self._credentials:
            return default

        keys = key.split('.')
        value = self._credentials

        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                    if value is None:
                        return default
                else:
                    return default
            return value
        except Exception:
            return default

    def set(self, key: str, value: Any, persist: bool = False) -> bool:
        """设置凭证值

        Args:
            key: 配置键，支持点号分隔的嵌套路径
            value: 要设置的值
            persist: 是否持久化到文件

        Returns:
            bool: 是否设置成功
        """
        try:
            keys = key.split('.')
            target = self._credentials
            for k in keys[:-1]:
                if k not in target:
                    target[k] = {}
                target = target[k]
            target[keys[-1]] = value

            if persist:
                return self._save_to_file()

            return True
        except Exception as e:
            logger.error(f"设置 credential 失败: {e}")
            return False

    def _save_to_file(self) -> bool:
        """将当前凭证状态保存到文件"""
        try:
            config_path = os.path.join(self._config_dir, 'credentials.yml')
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(
                    self._credentials,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False
                )
            logger.info("✅ 凭证配置已保存到文件")
            return True
        except Exception as e:
            logger.error(f"保存凭证配置失败: {e}")
            return False

    def reload(self):
        """重新加载凭证配置"""
        self._credentials = self._load_yaml_config('credentials.yml')
