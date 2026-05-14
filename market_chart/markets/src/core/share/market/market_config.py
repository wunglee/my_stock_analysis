"""
市场配置管理器（共享业务模块）

职责：管理不同市场的配置参数（从 YAML 配置文件读取）
定位：业务基础共享
"""

import logging
import os
from typing import Dict, Any, List

import yaml

from core.share.market.market_enums import MarketCode

logger = logging.getLogger(__name__)


class MarketConfig:
    """市场配置管理器（从 YAML 配置文件加载）
    
    职责：
    - 从 markets/config/{env}/market.yml 读取配置
    - 提供市场信息查询接口
    - 支持市场数据源的保存
    """
    
    def __init__(self, environment: str = 'dev', config_dir: str = None):
        """
        初始化市场配置管理器

        Args:
            environment: 环境名称（dev/test/prod），默认从环境变量读取
            config_dir: 配置文件目录路径，如果提供则直接使用，否则根据 environment 计算
        """
        self._config_dir = config_dir if config_dir else self._get_config_dir(environment)
        # 仅加载市场配置文件（风险和交易配置请使用 RiskConfig 和 TradeConfig）
        self._market_config = self._load_yaml_config('market.yml')

        # 解析市场基础配置
        self.market_registry = self._market_config.get('market_registry', {})
        self.market_sources = self._market_config.get('market_sources', {})
        self.market_limit = self._market_config.get('market_limit', {})
        self.trading_hours = self._market_config.get('trading_hours', {})
        self.market_mechanisms = self._market_config.get('market_mechanisms', {})
        self.default_indices = self._market_config.get('default_indices', {})

    def _get_config_dir(self, environment: str) -> str:
        """获取配置文件目录"""
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[4]
        config_dir = project_root / 'config' / environment
        return str(config_dir)

    def _load_yaml_config(self, filename: str) -> Dict[str, Any]:
        """通用YAML配置加载方法
        
        Args:
            filename: 配置文件名
        
        Returns:
            配置字典，如果文件不存在则返回空字典
        """
        try:
            config_path = os.path.join(self._config_dir, filename)
            
            if not os.path.exists(config_path):
                logger.warning(f"未找到配置文件: {config_path}，使用空配置")
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            logger.info(f"✅ {filename} 加载成功: {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"加载{filename}失败: {e}")
            return {}
    
    def _load_market_config(self) -> Dict[str, Any]:
        """从 YAML 文件加载市场配置（弃用，保留以向后兼容）"""
        return self._load_yaml_config('market.yml')
    
    def __post_init__(self):
        """数据验证"""
        if not isinstance(self.market_sources, dict):
            raise ValueError("market_sources 必须是字典类型")
    
    def save_market_sources(self, market_sources: Dict[str, str]) -> bool:
        """
        保存市场数据源映射到配置文件
        
        Args:
            market_sources: 市场到数据源的映射字典 {market_code: provider_id}
        
        Returns:
            bool: 是否保存成功
        
        Examples:
            >>> mc = MarketConfig()
            >>> mc.save_market_sources({'CN': 'akshare', 'US': 'yahoo'})
            True
        """
        try:
            market_yml_path = os.path.join(self._config_dir, 'market.yml')
            
            # 读取现有配置
            if os.path.exists(market_yml_path):
                with open(market_yml_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
            else:
                config_data = {}
            
            # 更新 market_sources
            config_data['market_sources'] = market_sources
            
            # 写入文件
            with open(market_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            logger.info(f"✅ 市场数据源配置保存成功: {market_sources}")
            
            # 更新内存中的配置
            self.market_sources = market_sources
            self._market_config['market_sources'] = market_sources
            
            return True
            
        except Exception as e:
            logger.error(f"保存市场数据源配置失败: {e}")
            return False
    
    def get_market_info(self, market_code: str) -> Dict[str, Any]:
        """获取市场基本信息"""
        return self.market_registry.get(market_code, {})
    
    def get_default_indices(self, market_code: str = None) -> Dict[str, Any]:
        """获取默认指数配置
        
        Args:
            market_code: 市场代码，如果为None则返回所有市场的默认指数
            
        Returns:
            默认指数配置字典
        """
        if market_code:
            return self.default_indices.get(market_code, {})
        else:
            return self.default_indices
    
    def validate_market_config(self, config: Dict) -> List[str]:
        """验证市场配置有效性（使用枚举）"""
        errors = []
        market_code = config.get('market_code', MarketCode.CN.value)
        
        # 使用枚举验证市场代码
        if not MarketCode.is_valid(market_code):
            errors.append(f"不支持的市场类型: {market_code}, 支持: {MarketCode.get_all_codes()}")
        
        market_configs = config.get('market_configs', {})
        if market_code not in market_configs:
            errors.append(f"缺少{market_code}市场的具体配置")
        
        return errors

    def generate_config_template(self, market_type: str) -> Dict[str, Any]:
        """生成配置模板（使用枚举验证）"""
        # 验证市场类型
        if not MarketCode.is_valid(market_type):
            logger.warning(f"不支持的市场类型{market_type}，回退到CN")
            market_type = MarketCode.CN.value
        
        market_info = self.market_registry[market_type]
        
        # 业务参数配置
        base_template = {
            'market_type': market_type,
            'trading_days_per_year': market_info.get('default_trading_days', 252),
            'market_configs': {
                market_type: self._build_market_specific_config(market_type, market_info)
            },
            'confidence_levels': {
                'daily_monitoring': 0.95,
                'risk_limit': 0.99,
                'regulatory_reporting': 0.99
            },
            'dynamic_risk_free_rate': None,
            'log_level': 'INFO',
            'performance_monitoring': {
                'enable_calculation_timing': True,
                'enable_memory_monitoring': False,
                'sample_size_warning_threshold': 50
            }
        }
        
        return base_template
    
    def _build_market_specific_config(self, market_code: str, market_info: Dict) -> Dict[str, Any]:
        """构建市场特定配置（仅包含市场基础信息）
        
        注意：
        - 风险参数请使用 RiskConfig.get_risk_parameters(market_code)
        - 交易成本请使用 TradeConfig.get_trade_cost(market_code)
        - 市场监控请使用 RiskConfig.get_market_monitoring(market_code)
        """
        config: Dict[str, Any] = {
            'trading_days': market_info.get('default_trading_days', 252),
        }
        
        # 从 market.yml 读取市场机制配置
        market_mech = self.market_mechanisms.get(market_code, {})
        if market_mech:
            config.update({
                'has_limit_up_down': market_mech.get('has_limit_up_down'),
                'price_limit': market_mech.get('price_limit'),
                'halt_risk_factor': market_mech.get('halt_risk_factor'),
            })
            
            # CN 特有配置
            if market_code == MarketCode.CN.value:
                if 'limit_thresholds' in market_mech:
                    config['limit_thresholds'] = market_mech['limit_thresholds']
                if 'consecutive_limit_days_p95' in market_mech:
                    config['consecutive_limit_days_p95'] = market_mech['consecutive_limit_days_p95']
            
            # US 特有配置
            if market_code == MarketCode.US.value:
                if 'circuit_breaker_levels' in market_mech:
                    config['circuit_breaker_levels'] = market_mech['circuit_breaker_levels']
                if 'luld_threshold' in market_mech:
                    config['luld_threshold'] = market_mech['luld_threshold']
                if 'luld_window' in market_mech:
                    config['luld_window'] = market_mech['luld_window']
        
        # 从 trading_hours 读取交易时间
        trading_hours = self.trading_hours.get(market_code, {})
        if trading_hours:
            config['trading_hours'] = {
                'regular': f"{trading_hours.get('open', '09:30')}-{trading_hours.get('close', '16:00')}",
                'pre_market': '',
                'after_hours': ''
            }
            # 处理午休
            if trading_hours.get('has_lunch_break'):
                config['trading_hours']['regular'] = (
                    f"{trading_hours.get('open', '09:30')}-{trading_hours.get('lunch_start', '12:00')},"
                    f"{trading_hours.get('lunch_end', '13:00')}-{trading_hours.get('close', '16:00')}"
                )
        
        return config