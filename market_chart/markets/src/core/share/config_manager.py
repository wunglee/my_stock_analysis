"""
配置管理器（单例模式）

职责：确定配置目录路径，实例化并协调各专项配置管理器
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.share.credentials_config import CredentialsConfig
from core.share.data_provider_config import DataProviderConfig
from core.share.database_config import DatabaseConfig
from core.share.market.market_config import MarketConfig

logger = logging.getLogger('Infrastructure.ConfigManager')


class ConfigManager:
    """
    配置管理器（单例模式）

    职责：
    - 确定配置目录路径
    - 实例化并协调各专项配置管理器
    - 提供统一的配置访问接口（向后兼容）

    Note:
        使用单例模式确保全局只有一个实例，避免多个watchdog监听器冲突
    """

    _instance = None
    _lock = None
    _observer = None
    environment: str

    def __new__(cls, config_file: Optional[str] = None, environment: Optional[str] = None):
        if cls._instance is None:
            if cls._lock is None:
                import threading
                cls._lock = threading.Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ConfigManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, environment='dev'):
        if getattr(self, '_initialized', False):
            return
        self.environment = environment
        config_dir = str(self._get_config_dir())

        self._load_config()

        self._credentials_config = CredentialsConfig(config_dir)
        self._data_provider_config = DataProviderConfig(config_dir)
        self._database_config = DatabaseConfig(config_dir)
        self._market_config = MarketConfig(config_dir=config_dir)

        if environment != 'test' and ConfigManager._observer is None:
            self._start_hot_reload_watcher()
        self._initialized = True

    def _get_config_dir(self) -> Path:
        """获取配置目录路径

        Returns:
            当前环境对应的配置目录路径，不存在则回退到基础配置目录
        """
        project_root = Path(__file__).resolve().parents[3]
        env_dir = project_root / 'config' / self.environment
        return env_dir if env_dir.exists() else project_root / 'config'

    def _load_config(self):
        """加载所有 YAML 配置到全局字典（兼容层）"""
        try:
            import glob
            config_dir = self._get_config_dir()
            loaded = {}
            yml_files = glob.glob(os.path.join(config_dir, '*.yml'))
            for yml_path in yml_files:
                config_key = os.path.splitext(os.path.basename(yml_path))[0]
                try:
                    with open(yml_path, 'r', encoding='utf-8') as f:
                        loaded[config_key] = yaml.safe_load(f) or {}
                except Exception as e:
                    logger.warning(f"跳过无效配置文件 {yml_path}: {e}")
            if loaded:
                self._config = loaded
                logger.info(f"从 YAML 加载配置 [{self.environment}]: {sorted(loaded.keys())}")
        except Exception as e:
            logger.warning(f"YAML配置加载失败: {e}")
            self._config = {}

    # ========== 专项配置管理器访问 ==========

    def get_credentials_config(self) -> CredentialsConfig:
        """获取凭证配置管理器"""
        return self._credentials_config

    def get_data_provider_config(self) -> DataProviderConfig:
        """获取数据提供者配置管理器"""
        return self._data_provider_config

    def get_database_config(self) -> DatabaseConfig:
        """获取数据库配置管理器"""
        return self._database_config

    def get_market_config(self) -> MarketConfig:
        """获取市场配置管理器"""
        return self._market_config

    # ========== 便捷代理方法（向后兼容） ==========

    def get_credential(self, key: str, default: Any = None) -> Any:
        """获取凭证值（代理到 CredentialsConfig）"""
        return self._credentials_config.get(key, default)

    def set_credential(self, key: str, value: Any, persist: bool = False) -> bool:
        """设置凭证值（代理到 CredentialsConfig）"""
        return self._credentials_config.set(key, value, persist)

    def get_provider_config(self) -> DataProviderConfig:
        """获取数据提供者配置（返回 DataProviderConfig 实例）"""
        return self._data_provider_config

    def get_trading_hours(self, market_code: str) -> Dict[str, Any]:
        """获取指定市场的交易时段配置"""
        hours = self._market_config.trading_hours.get(market_code, {})
        if not hours:
            logger.warning(f"未找到市场 {market_code} 的交易时段配置，使用默认值")
            return {
                'open': '09:30',
                'close': '15:00',
                'lunch_start': '11:30',
                'lunch_end': '13:00',
                'has_lunch_break': True,
                'timezone': 'Asia/Shanghai',
                'description': '默认交易时段'
            }
        return hours

    def get_provider_for_symbol(self, symbol: str) -> Optional[str]:
        """根据股票代码获取数据源ID"""
        from core.share.market.market_utils import MarketUtils
        market_code = MarketUtils.infer_market_from_symbol(symbol)
        provider_id = self._market_config.market_sources.get(market_code.value)
        if not provider_id:
            logger.warning(f"未找到市场 {market_code.value} 的数据源配置")
            return None
        return provider_id

    # ========== 通用配置访问（兼容层） ==========

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号分隔的嵌套键）"""
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """设置配置值（支持点号分隔的嵌套键，仅内存）"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def get_config_path(self, name: str) -> str:
        """获取配置文件绝对路径"""
        config_dir = self._get_config_dir()
        if not name.endswith(('.yml', '.yaml')):
            name = f"{name}.yml"
        return str(config_dir / name)

    # ========== 热重载 ==========

    def _start_hot_reload_watcher(self):
        """启动热加载监听器（全局单例）"""
        try:
            import threading
            import time
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class ConfigReloadHandler(FileSystemEventHandler):
                def __init__(self, config_manager):
                    self.config_manager = config_manager

                def on_modified(self, event):
                    if event.src_path.endswith(('.yml', '.yaml')):
                        logger.info(f"检测到配置文件变更: {event.src_path}")
                        time.sleep(0.1)
                        self.config_manager._reload_all()

            def watch_thread():
                watch_path = str(self._get_config_dir())
                event_handler = ConfigReloadHandler(self)
                ConfigManager._observer = Observer()
                ConfigManager._observer.schedule(event_handler, watch_path, recursive=False)
                ConfigManager._observer.start()
                logger.info(f"启动配置热加载监听: {watch_path}")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    if ConfigManager._observer:
                        ConfigManager._observer.stop()
                if ConfigManager._observer:
                    ConfigManager._observer.join()

            watcher = threading.Thread(target=watch_thread, daemon=True, name='ConfigHotReload')
            watcher.start()
        except ImportError:
            logger.info("未安装watchdog，跳过配置热加载")
        except Exception as e:
            logger.warning(f"配置热加载启动失败: {e}")

    def _reload_all(self):
        """重新加载所有配置"""
        self._load_config()
        config_dir = str(self._get_config_dir())
        self._credentials_config.reload()
        self._data_provider_config.reload()
        self._database_config.reload()
        self._market_config = MarketConfig(config_dir=config_dir)
        logger.info("所有配置已重新加载")
