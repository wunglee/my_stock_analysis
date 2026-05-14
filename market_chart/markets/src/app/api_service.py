"""市场数据RESTful API服务

提供市场数据相关的REST API接口：
- 图表数据 (K线 + 技术指标)
- 分时数据
- 市场配置管理
- 数据提供者管理
- 凭证管理
- 指数价格/收益率/事件窗口数据
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Any, Dict

import pandas as pd
import yaml
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from app.chart_data import ChartDataAssembler
from core.data.providers.base_provider import BaseDataProvider
from core.data.providers.factory import get_global_factory
from core.data.providers.protocols import TickRange
from core.data.providers.provider_selector import ProviderSelector
from core.share.config_manager import ConfigManager
from core.share.market.market_time_utils import MarketTimeUtils
from core.share.market.market_utils import MarketUtils
from core.signal.indicator_service import TechnicalIndicators


logger = logging.getLogger('App.APIService')


class DataQualityAPIService:
    """市场数据API服务 - 提供RESTful API接口"""

    def __init__(self,scheduler=None):
        self.scheduler = scheduler  # 调度器实例（可选）

        self.app = Flask(__name__, static_folder=None)

        # 启用CORS
        CORS(self.app)

        # 初始化Socket.IO（支持实时推送）
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=False,
            engineio_logger=False
        )
        logger.info("Socket.IO服务已初始化")

        # 初始化核心组件
        self.config_manager = ConfigManager()
        self.provider_factory = get_global_factory()
        self.provider_selector = ProviderSelector(self.config_manager)

        self._setup_routes()
        self._register_mock_routes()  # 注册Mock端点
        self._setup_socketio_handlers()

    def _create_chart_assembler(self, symbol: str, timeframe: str = 'daily') -> ChartDataAssembler:
        """动态创建图表数据组装器
        
        Args:
            symbol: 股票/指数代码
            timeframe: 时间周期
        
        Returns:
            ChartDataAssembler: 图表数据组装器实例
        """

        # 1. 使用领域层服务选择数据提供者
        data_provider = self.provider_selector.select_provider_for_symbol(
            symbol=symbol,
            provider_factory=self.provider_factory
        )

        # 2. 推断市场（用于创建指标服务）
        market_code = MarketUtils.infer_market_from_symbol(symbol)
        market = market_code.value

        # 3. 创建指标服务（根据市场）
        indicator_service = TechnicalIndicators(market=market, timeframe=timeframe)

        # 4. 创建图表数据组装器
        return ChartDataAssembler(
            data_provider=data_provider,
            indicator_service=indicator_service
        )

    def _create_provider_instance(self, provider: Dict[str, Any], credentials: Dict[str, Any] = None,
                                  proxy_config: Dict[str, Any] = None):
        """创建数据提供者实例（使用 factory.py 的功能）
        
        Args:
            provider: 数据提供者配置字典
            credentials: 凭证信息（可选）
            proxy_config: 代理配置（可选）
        
        Returns:
            数据提供者实例，失败返回 None
        
        Note:
            该方法利用 DataProviderFactory 的动态加载功能，
            并支持传入自定义凭证和代理配置。
        """
        try:
            provider_id = provider.get('id')
            if not provider_id:
                logger.error(f"数据提供者配置不完整: {provider}")
                return None

            # 使用 DataProviderFactory 的 _get_provider_class 逻辑
            # 但需要支持自定义凭证和代理，所以直接使用动态导入
            adapter_module = provider.get('adapter_module')
            adapter_class = provider.get('adapter_class')

            if not adapter_module or not adapter_class:
                logger.error(f"Provider '{provider_id}' 配置不完整：缺少 adapter_module 或 adapter_class")
                return None

            # 动态导入模块（与 factory.py 一致）
            module = importlib.import_module(adapter_module)
            provider_class = getattr(module, adapter_class)

            # 创建实例（支持自定义参数）
            kwargs = {}
            if credentials:
                kwargs['credentials'] = credentials
            if proxy_config:
                kwargs['proxy_config'] = proxy_config

            instance = provider_class(**kwargs)
            logger.debug(f"创建数据提供者实例成功: {provider_id}")
            return instance

        except Exception as e:
            logger.error(f"创建数据提供者实例失败: {e}", exc_info=True)
            return None

    def _setup_routes(self):
        """设置API路由 - 完整生产实现"""

        @self.app.route('/api/v1/health', methods=['GET'])
        def health_check():
            """健康检查端点"""
            return jsonify({
                'status': 'healthy',
                'timestamp': pd.Timestamp.now().isoformat()
            })

        @self.app.route('/api/v1/chart/data', methods=['GET'])
        def get_chart_data():
            """获取合并的图表数据（K线+技术指标+事件）【真实数据】
            
            查询参数：
                - symbol: 股票/指数代码（必需）
                - period: 周期（daily/weekly/monthly，默认 daily）
                - count: 数据条数（默认 120）
                - before: 获取此日期之前的数据（YYYY-MM-DD，已获取的K线日期，市场本地时间，可选）
                - indicators: 需要的指标，逗号分隔（默认 'all'）
                               支持: vol, macd, rsi, kdj, obv
            
            返回示例：
            {
                "status": "success",
                "data": {
                    "kline": [
                        {
                            "date": "2024-01-01",
                            "open": 100.0,
                            "high": 105.0,
                            "low": 99.0,
                            "close": 103.0,
                            "volume": 1000000,
                            "ma5": 102.0,
                            "ma10": 101.5,
                            "ma20": 100.8
                        }
                    ],
                    "indicators": {
                        "vol": [{"date": "2024-01-01", "value": 1000000}],
                        "macd": [{"date": "2024-01-01", "macd": 0.5, "signal": 0.3, "histogram": 0.2}],
                        "rsi": [{"date": "2024-01-01", "value": 60.0}],
                        "kdj": [{"date": "2024-01-01", "k": 70.0, "d": 65.0, "j": 75.0}],
                        "obv": [{"date": "2024-01-01", "value": 5000000}]
                    },
                    "events": [
                        {
                            "date": "2024-01-05",
                            "type": "market_crash",
                            "title": "暴跌 5.2%",
                            "decline_pct": -5.2,
                            "price": 98.0,
                            "impact": "negative",
                            "severity": "high"
                        }
                    ],
                    "chipDistribution": {
                        "2024-01-01": {
                            "bins": [
                                {"price": 99.5, "volume": 150000, "percentage": 15.0},
                                {"price": 100.5, "volume": 350000, "percentage": 35.0}
                            ],
                            "minPrice": 99.0,
                            "maxPrice": 101.0,
                            "totalVolume": 1000000
                        }
                    },
                    "needs_realtime_kline": false
                }
            }
            """
            try:
                # 获取查询参数
                symbol = request.args.get('symbol')
                if not symbol:
                    return jsonify({
                        'status': 'error',
                        'message': '缺少必需参数: symbol',
                        'error_code': 'MISSING_PARAMETER'
                    }), 400

                period = request.args.get('period', 'daily')
                count = request.args.get('count', 120, type=int)
                before_str = request.args.get('before')  # K线日期（市场本地时间）

                # 🔧 before 是已获取的K线日期，本身就是市场本地时间，无需时区转换
                before = None
                if before_str:
                    try:
                        before=MarketTimeUtils.to_market_time_by_symbol(pd.Timestamp(before_str), symbol)
                    except Exception as e:
                        return jsonify({
                            'status': 'error',
                            'message': f'无效的日期格式: {str(e)}',
                            'error_code': 'INVALID_DATE_FORMAT'
                        }), 400
                
                indicators = request.args.get('indicators', 'all')

                # 参数验证
                if period not in ['daily', 'weekly', 'monthly']:
                    return jsonify({
                        'status': 'error',
                        'message': f'无效的周期参数: {period}，支持: daily/weekly/monthly',
                        'error_code': 'INVALID_PERIOD'
                    }), 400

                if count <= 0 or count > 1000:
                    return jsonify({
                        'status': 'error',
                        'message': f'数据条数必须在 1-1000 之间，当前: {count}',
                        'error_code': 'INVALID_COUNT'
                    }), 400

                # 使用真实数据源
                logger.info(f"🎯 使用真实数据源: {symbol}")
                chart_assembler = self._create_chart_assembler(symbol, timeframe=period)

                # 🔧 关键修复：将UTC时间转换为不带时区的市场本地时间
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)

                # 调用组装器
                chart_data = chart_assembler.assemble_chart_data(
                    symbol=symbol,
                    period=period,
                    count=count,
                    before=before,
                    indicators=indicators,
                    market_local_time=market_local_time
                )

                # 使用目标市场时区的时间戳
                timestamp_with_tz = MarketTimeUtils.get_market_time_now(symbol)
                return jsonify({
                    'status': 'success',
                    'data': chart_data,
                    'metadata': {
                        'symbol': symbol,
                        'period': period,
                        'count': len(chart_data.get('kline', [])),
                        'indicators': list(chart_data.get('indicators', {}).keys()),
                        'events_count': len(chart_data.get('events', [])),
                        'chipDistribution_count': len(chart_data.get('chipDistribution', {}))
                    },
                    'timestamp': timestamp_with_tz.isoformat()
                })

            except ValueError as e:
                logger.error(f"图表数据获取参数错误: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'INVALID_PARAMETER'
                }), 400

            except RuntimeError as e:
                logger.error(f"图表数据组装失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CHART_DATA_ASSEMBLY_FAILED'
                }), 500

            except Exception as e:
                logger.error(f"获取图表数据失败: {e}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'获取图表数据失败: {str(e)}',
                    'error_code': 'CHART_DATA_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/intraday/data', methods=['GET'])
        def get_intraday_data():
            """获取分时图数据（真实数据）
            
            查询参数：
                - symbol: 证券代码（必需）
                - tick_range: TickRange JSON（可选）
            
            返回示例：
            {
                "status": "success",
                "data": {
                    "symbol": "000001.SH",
                    "name": "上证指数",
                    "current_price": 3125.50,
                    "yesterday_close": 3120.00,
                    "change": 5.50,
                    "change_percent": 0.18,
                    "times": ["09:30", "09:31", ...],
                    "prices": [3121.0, 3122.5, ...],
                    "volumes": [12000, 15000, ...],
                    "avg_prices": [3121.0, 3121.75, ...],
                    "order_book": {
                        "bids": [{"price": 3125.49, "volume": 2000}, ...],
                        "asks": [{"price": 3125.51, "volume": 1800}, ...]
                    },
                    "trade_records": [
                        {"time": "14:59:50", "price": 3125.50, "volume": 100, "type": "buy"},
                        ...
                    ]
                },
                "timestamp": "2025-12-12T10:24:29.573456"
            }
            """
            try:
                symbol = request.args.get('symbol')
                if not symbol:
                    return jsonify({
                        'status': 'error',
                        'message': '缺少必需参数: symbol',
                        'error_code': 'MISSING_PARAMETER'
                    }), 400

                # 解析 tick_range（可选）
                tick_range_str = request.args.get('tick_range')
                tick_range = None

                if tick_range_str:
                    try:
                        tick_range_dict = json.loads(tick_range_str)

                        # 验证字段
                        required_fields = ['start_time', 'end_time', 'period_seconds']
                        for field in required_fields:
                            if field not in tick_range_dict:
                                return jsonify({
                                    'status': 'error',
                                    'message': f'tick_range缺少字段: {field}',
                                    'error_code': 'INVALID_TICK_RANGE'
                                }), 400

                        # 转换为 TickRange 对象
                        tick_range = TickRange(
                            start_time=MarketTimeUtils.to_market_time_by_symbol(pd.Timestamp(tick_range_dict['start_time']), symbol),
                            end_time=MarketTimeUtils.to_market_time_by_symbol(pd.Timestamp(tick_range_dict['end_time']), symbol),
                            period_seconds=int(tick_range_dict['period_seconds'])
                        )
                    except (json.JSONDecodeError, ValueError) as e:
                        return jsonify({
                            'status': 'error',
                            'message': f'解析tick_range失败: {str(e)}',
                            'error_code': 'INVALID_TICK_RANGE_FORMAT'
                        }), 400

                # 📊 真实模式：调用 ChartDataAssembler（会调用 akshare_provider）
                logger.info(f"📊 真实模式: symbol={symbol}, tick_range={'已提供' if tick_range else '未提供'}")
                
                chart_assembler = self._create_chart_assembler(symbol, timeframe='daily')
                intraday_data = chart_assembler.assemble_intraday_data(
                    symbol=symbol,
                    tick_range=tick_range
                )

                # 使用目标市场时区的时间戳
                timestamp_with_tz = MarketTimeUtils.get_market_time_now(symbol)
                return jsonify({
                    'status': 'success',
                    'data': intraday_data,
                    'timestamp': timestamp_with_tz.isoformat()
                })

            except ValueError as e:
                # 数据验证错误（如盘后数据不完整），返回400
                logger.warning(f"数据验证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'DATA_VALIDATION_FAILED'
                }), 400

            except Exception as e:
                logger.error(f"获取分时数据失败: {e}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'获取分时数据失败: {str(e)}',
                    'error_code': 'INTRADAY_DATA_FAILED'
                }), 500


        # ============================================================
        # 市场数据源配置API
        # ============================================================

        @self.app.route('/api/v1/markets/config', methods=['GET'])
        def get_markets_config():
            """获取所有市场配置信息（从配置文件读取）"""
            try:
                # 从配置文件读取真实配置
                data_provider_config = self.config_manager.get_provider_config()

                # 从 market.yml 的 market_registry 读取市场列表（包含UI展示信息）
                market_config = self.config_manager.get_market_config()
                market_registry = market_config.market_registry or {}
                trading_hours_config = market_config.trading_hours or {}

                # 从 market_registry 生成 UI 展示数据
                markets = []
                for code, info in market_registry.items():
                    # 获取详细的交易时间配置
                    detailed_trading_hours = trading_hours_config.get(code, {})
                    
                    market_data = {
                        'code': code,
                        'name': info.get('display_name', info.get('name', code)),  # 优先使用 display_name
                        'icon': info.get('icon', ''),
                        'timezone': info.get('timezone', ''),  # 添加时区信息
                        'currency': info.get('currency', ''),   # 添加货币信息
                        'trading_hours': info.get('trading_hours', ''),  # 添加交易时间信息
                        'detailed_trading_hours': detailed_trading_hours  # 添加详细交易时间配置
                    }
                    
                    # 不再传递 has_lunch_break 字段，前端将通过交易时段是否唯一判断
                    markets.append(market_data)

                # 从 data_provider_config.yml 读取 providers 配置
                providers_raw = data_provider_config.providers or []

                # 转换为前端需要的格式（过滤掉未实现的适配器）
                providers = []
                for p in providers_raw:
                    # 过滤掉未实现的适配器（adapter_module 和 adapter_class 为 null 的）
                    adapter_module = p.get('adapter_module')
                    adapter_class = p.get('adapter_class')
                    if not adapter_module or not adapter_class or adapter_module == 'null' or adapter_class == 'null':
                        continue  # 跳过未实现的适配器

                    # 获取配置文件中的状态（已移除聚合数据源）
                    # TODO: 实现新的测试状态获取机制
                    provider_id = p.get('id')
                    test_status = p.get('status', 'untested')  # 使用配置文件中的状态
                    is_available = test_status == 'passed'

                    provider_data = {
                        'id': p.get('id'),
                        'name': p.get('name'),
                        'type': p.get('type', '未知'),
                        'status': test_status,  # 使用实时状态
                        'available': is_available,  # 添加 bool 字段供前端使用
                        'markets': p.get('markets', []),
                        'needsConfig': p.get('requires_auth', False),
                        'params': []
                    }

                    # 如果需要配置，添加参数定义
                    if p.get('requires_auth'):
                        auth_type = p.get('auth_type', 'api_key')
                        if auth_type == 'token':
                            provider_data['params'] = [
                                {
                                    'name': 'token',
                                    'label': f"{p.get('name')} Token",
                                    'type': 'password',
                                    'required': True,
                                    'placeholder': f"在 {p.get('registration', '')} 注册获取"
                                }
                            ]
                        else:  # api_key
                            provider_data['params'] = [
                                {
                                    'name': 'api_key',
                                    'label': 'API Key',
                                    'type': 'password',
                                    'required': True,
                                    'placeholder': f"在 {p.get('registration', '')} 注册获取"
                                }
                            ]

                    providers.append(provider_data)
                data_market_config = self.config_manager.get_market_config()
                # 市场数据源配置
                market_sources = data_market_config.market_sources or {}

                # 从真实凭证文件读取凭证状态
                # 使用 ConfigManager 获取配置路径（封装环境逻辑）
                config_manager_temp = ConfigManager()
                credentials_yml_path = config_manager_temp.get_config_path('credentials')

                # 读取凭证文件
                credentials_data = {}
                if os.path.exists(credentials_yml_path):
                    try:
                        with open(credentials_yml_path, 'r', encoding='utf-8') as f:
                            credentials_data = yaml.safe_load(f) or {}
                    except Exception as e:
                        logger.warning(f"读取凭证文件失败: {e}")

                # 生成凭证状态
                credentials = {}
                for p in providers_raw:
                    provider_id = p.get('id')
                    # 免费数据源标记为已配置
                    if not p.get('requires_auth'):
                        credentials[provider_id] = {'configured': True}
                    else:
                        # 检查凭证文件中是否存在
                        credentials[provider_id] = {
                            'configured': provider_id in credentials_data
                        }

                return jsonify({
                    'status': 'success',
                    'data': {
                        'markets': markets,
                        'providers': providers,
                        'market_sources': market_sources,
                        'credentials': credentials
                    },
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"获取市场配置失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'MARKETS_CONFIG_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/markets/config', methods=['PUT'])
        def update_markets_config():
            """更新市场数据源配置（真实保存）"""
            try:
                data = request.get_json()
                if not data or 'market_sources' not in data:
                    return jsonify({
                        'status': 'error',
                        'message': '缺少 market_sources 字段',
                        'error_code': 'INVALID_REQUEST_DATA'
                    }), 400

                market_sources = data['market_sources']

                # 使用 ConfigManager 的验证和保存方法
                try:
                    self.config_manager.get_market_config().save_market_sources(market_sources)

                    return jsonify({
                        'status': 'success',
                        'message': '市场配置已保存',
                        'data': {
                            'updated_markets': list(market_sources.keys()),
                            'config_file': self.config_manager.get_config_path('markets')
                        },
                        'timestamp': pd.Timestamp.now().isoformat()
                    })
                except ValueError as ve:
                    # 验证失败
                    return jsonify({
                        'status': 'error',
                        'message': str(ve),
                        'error_code': 'MARKET_VALIDATION_FAILED'
                    }), 400
            except Exception as e:
                logger.error(f"更新市场配置失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'MARKETS_CONFIG_UPDATE_FAILED'
                }), 500

        @self.app.route('/api/v1/markets/default-indices', methods=['GET'])
        def get_default_indices():
            """获取各市场的默认指数/股票列表"""
            try:
                # 从配置文件读取市场配置
                market_config = self.config_manager.get_market_config()
                
                # 获取默认指数配置
                default_indices = getattr(market_config, 'default_indices', {})
                
                # 转换为前端需要的格式（将code字段映射为id字段）
                result = {}
                for market_code, indices in default_indices.items():
                    result[market_code] = []
                    for index in indices:
                        # 将配置文件中的code字段映射为前端需要的id字段
                        result[market_code].append({
                            'id': index.get('code', ''),
                            'name': index.get('name', ''),
                            'type': index.get('type', 'index')
                        })
                
                return jsonify({
                    'status': 'success',
                    'data': result,
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"获取默认指数列表失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'DEFAULT_INDICES_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>/credentials', methods=['POST'])
        def save_provider_credentials(provider_id):
            """保存数据源凭证（调用领域层 Provider 的保存方法）"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'status': 'error',
                        'message': '无效的请求数据',
                        'error_code': 'INVALID_REQUEST_DATA'
                    }), 400

                # 使用环境变量或默认 dev

                # 使用 BaseDataProvider 的通用方法保存凭证
                success = BaseDataProvider.save_credentials(provider_id, data)

                if success:
                    # 重新加载配置
                    self.config_manager._load_config()

                    return jsonify({
                        'status': 'success',
                        'message': f'{provider_id} 凭证已保存，请重新测试连接',
                        'data': {
                            'provider_id': provider_id,
                            'configured': True,
                            'test_status': 'success'
                        },
                        'timestamp': pd.Timestamp.now().isoformat()
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': '保存凭证失败',
                        'error_code': 'CREDENTIALS_SAVE_FAILED'
                    }), 500

            except Exception as e:
                logger.error(f"保存凭证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIALS_SAVE_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>/credentials', methods=['DELETE'])
        def delete_provider_credentials(provider_id):
            """删除数据源凭证（调用领域层 Provider 的删除方法）"""
            try:
                # 使用环境变量或默认 dev

                # 使用 BaseDataProvider 的通用方法删除凭证
                success = BaseDataProvider.delete_credentials(provider_id)

                if success:
                    # 使用中国市场时区的时间戳
                    timestamp_with_tz = MarketTimeUtils.get_market_time_now('000001.SH')
                    return jsonify({
                        'status': 'success',
                        'message': f'{provider_id} 凭证已删除',
                        'timestamp': pd.Timestamp.now().isoformat()
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': '删除凭证失败',
                        'error_code': 'CREDENTIALS_DELETE_FAILED'
                    }), 500

            except Exception as e:
                logger.error(f"删除凭证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIALS_DELETE_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>/test', methods=['POST'])
        def test_provider_connection(provider_id):
            """测试数据源连接（调用领域层 Provider 的测试方法）"""
            try:
                # 获取请求中的测试参数（如API Key）
                test_params = request.get_json() or {}

                # 使用 factory 获取 provider 类并调用 test_provider 方法
                factory = get_global_factory()

                try:
                    # 创建 provider 实例
                    provider = factory.get(provider_id)

                    # 转换参数：credentials → credential
                    # test_provider 方法签名：test_provider(provider_id, credential: str)
                    # proxy 从配置文件读取，不作为参数传递
                    credentials_dict = test_params.get('credentials', {})

                    # 提取 credential 字符串（可能是 api_key 或 token）
                    credential = None
                    if credentials_dict:
                        # 优先使用 api_key，其次使用 token
                        credential = credentials_dict.get('api_key') or credentials_dict.get('token')

                    # 调用 provider 类的 test_provider 方法
                    if credential:
                        result = provider.__class__.test_provider(provider_id, credential=credential)
                    else:
                        # 免费数据源不需要 credential
                        result = provider.__class__.test_provider(provider_id, credential='')
                except Exception as e:
                    result = {
                        'status': 'error',
                        'test_result': 'failed',
                        'available': False,
                        'message': str(e),
                        'timestamp': pd.Timestamp.now().isoformat()
                    }

                # 根据结果返回 HTTP 状态码
                if result['status'] == 'error':
                    return jsonify(result), 500
                else:
                    return jsonify(result)

            except Exception as e:
                logger.error(f"测试连接失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'test_result': 'failed',
                    'error_code': 'TEST_CONNECTION_FAILED'
                }), 500

        # ============================================================
        # 旧API：数据提供者能力暴露（保留兼容）
        # ============================================================

        @self.app.route('/api/v1/providers', methods=['GET'])
        def get_providers():
            """获取所有数据源配置（只返回已实现的数据源）"""
            try:
                config = self.config_manager.get('data_provider', {})
                all_providers = config.get('providers', [])
                primary_source = config.get('primary_source', 'mock')

                # 过滤掉未实现的适配器（adapter_module 和 adapter_class 为 null 的）
                implemented_providers = [
                    p for p in all_providers
                    if p.get('adapter_module') and p.get('adapter_class')
                       and p.get('adapter_module') != 'null' and p.get('adapter_class') != 'null'
                ]

                return jsonify({
                    'status': 'success',
                    'providers': implemented_providers,
                    'primary_source': primary_source,
                    'total': len(implemented_providers),
                    'total_configured': len(all_providers),  # 配置文件中的总数
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"获取数据源列表失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'PROVIDERS_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>', methods=['GET'])
        def get_provider(provider_id):
            """获取指定数据源配置"""
            try:
                config = self.config_manager.get('data_provider', {})
                providers = config.get('providers', [])

                provider = next((p for p in providers if p.get('id') == provider_id or p.get('name') == provider_id),
                                None)

                if not provider:
                    return jsonify({
                        'status': 'error',
                        'message': f'数据源不存在: {provider_id}',
                        'error_code': 'PROVIDER_NOT_FOUND'
                    }), 404

                return jsonify({
                    'status': 'success',
                    'provider': provider,
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"获取数据源配置失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'PROVIDER_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/providers', methods=['POST'])
        def create_provider():
            """创建新数据源"""
            try:
                new_provider = request.get_json()
                if not new_provider:
                    return jsonify({
                        'status': 'error',
                        'message': '无效的数据源配置',
                        'error_code': 'INVALID_PROVIDER_DATA'
                    }), 400

                # 验证必填字段
                required_fields = ['name', 'type']
                for field in required_fields:
                    if field not in new_provider:
                        return jsonify({
                            'status': 'error',
                            'message': f'缺少必填字段: {field}',
                            'error_code': 'MISSING_REQUIRED_FIELD'
                        }), 400

                config = self.config_manager.get('data_provider', {})
                providers = config.get('providers', [])

                # 检查是否已存在
                if any(p.get('name') == new_provider['name'] for p in providers):
                    return jsonify({
                        'status': 'error',
                        'message': f'数据源已存在: {new_provider["name"]}',
                        'error_code': 'PROVIDER_ALREADY_EXISTS'
                    }), 409

                # 添加默认字段
                new_provider.setdefault('enabled', True)
                new_provider.setdefault('priority', len(providers) + 1)
                new_provider.setdefault('created_at', pd.Timestamp.now().isoformat())

                providers.append(new_provider)
                config['providers'] = providers

                self.config_manager.update({'data': config})
                logger.info(f"创建数据源成功: {new_provider['name']}")

                return jsonify({
                    'status': 'success',
                    'message': '数据源创建成功',
                    'provider': new_provider,
                    'timestamp': pd.Timestamp.now().isoformat()
                }), 201
            except Exception as e:
                logger.error(f"创建数据源失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'PROVIDER_CREATE_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>', methods=['PUT'])
        def update_provider(provider_id):
            """更新数据源配置"""
            try:
                updated_data = request.get_json()
                if not updated_data:
                    return jsonify({
                        'status': 'error',
                        'message': '无效的更新数据',
                        'error_code': 'INVALID_UPDATE_DATA'
                    }), 400

                config = self.config_manager.get('data_provider', {})
                providers = config.get('providers', [])

                provider_index = next(
                    (i for i, p in enumerate(providers) if p.get('id') == provider_id or p.get('name') == provider_id),
                    None)

                if provider_index is None:
                    return jsonify({
                        'status': 'error',
                        'message': f'数据源不存在: {provider_id}',
                        'error_code': 'PROVIDER_NOT_FOUND'
                    }), 404

                # 更新字段
                providers[provider_index].update(updated_data)
                providers[provider_index]['updated_at'] = pd.Timestamp.now().isoformat()

                config['providers'] = providers
                self.config_manager.update({'data': config})
                logger.info(f"更新数据源成功: {provider_id}")

                return jsonify({
                    'status': 'success',
                    'message': '数据源更新成功',
                    'provider': providers[provider_index],
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"更新数据源失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'PROVIDER_UPDATE_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>', methods=['DELETE'])
        def delete_provider(provider_id):
            """删除数据源"""
            try:
                config = self.config_manager.get('data_provider', {})
                providers = config.get('providers', [])

                provider_index = next(
                    (i for i, p in enumerate(providers) if p.get('id') == provider_id or p.get('name') == provider_id),
                    None)

                if provider_index is None:
                    return jsonify({
                        'status': 'error',
                        'message': f'数据源不存在: {provider_id}',
                        'error_code': 'PROVIDER_NOT_FOUND'
                    }), 404

                deleted_provider = providers.pop(provider_index)
                config['providers'] = providers

                self.config_manager.update({'data': config})
                logger.info(f"删除数据源成功: {provider_id}")

                return jsonify({
                    'status': 'success',
                    'message': '数据源删除成功',
                    'deleted_provider': deleted_provider,
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"删除数据源失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'PROVIDER_DELETE_FAILED'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>/test', methods=['POST'])
        def test_provider(provider_id):
            """测试数据源连接（使用临时凭证）"""
            try:
                config = self.config_manager.get('data_provider', {})
                providers = config.get('providers', [])

                provider = next((p for p in providers if p.get('id') == provider_id or p.get('name') == provider_id),
                                None)

                if not provider:
                    return jsonify({
                        'status': 'error',
                        'message': f'数据源不存在: {provider_id}',
                        'error_code': 'PROVIDER_NOT_FOUND'
                    }), 404

                # 获取前端传入的临时凭证和代理设置（如果有）
                request_data = request.get_json() or {}
                temp_credentials = request_data.get('credentials', {})
                proxy_config = request_data.get('proxy', {})
                test_symbol = request_data.get('test_symbol', 'AAPL.US')
                # 🔧 统一使用 pd.Timestamp，不使用字符串日期
                start_date = pd.to_datetime(request_data.get('start_date', '2023-01-01'))
                start_date=MarketTimeUtils.to_market_time_by_symbol(start_date,test_symbol)
                end_date = pd.to_datetime(request_data.get('end_date', '2023-12-31'))
                end_date=MarketTimeUtils.to_market_time_by_symbol(end_date, test_symbol)

                # 如果没有传入代理配置，使用空配置
                if not proxy_config:
                    proxy_config = {}

                # 创建临时实例进行测试
                test_instance = self._create_provider_instance(provider, temp_credentials, proxy_config)

                if not test_instance:
                    return jsonify({
                        'status': 'error',
                        'message': f'无法创建数据源实例: {provider_id}',
                        'error_code': 'INSTANCE_CREATION_FAILED'
                    }), 500

                requires_auth = test_instance.requires_auth()
                credentials = test_instance.credentials

                # 执行测试
                start_time = MarketTimeUtils.get_market_time_now(test_symbol)
                test_data = test_instance.test_connection(
                    test_symbol=test_symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                # 计算延迟（毫秒）
                end_time = MarketTimeUtils.get_market_time_now(test_symbol)
                latency_ms = round((end_time - start_time).total_seconds() * 1000, 2)

                # 检查测试数据
                if hasattr(test_data, 'to_dataframe'):
                    test_data_df = test_data.to_dataframe()
                    is_empty = test_data_df.empty
                    data_count = len(test_data_df)
                else:
                    is_empty = test_data.empty if test_data is not None else True
                    data_count = len(test_data) if test_data is not None else 0

                if test_data is None or is_empty:
                    # 测试失败：连接成功但返回空数据
                    is_available = False
                    message = f'{provider_id} 连接成功，但返回空数据'
                    logger.warning(f"{provider_id} 测试警告: {message}")

                    result_data = {
                        'status': 'error',
                        'test_result': 'failed',
                        'available': is_available,
                        'message': message,
                        'details': {
                            'test_symbol': test_symbol,
                            'date_range': f'{start_date} to {end_date}',
                            'latency_ms': latency_ms
                        }
                    }
                else:
                    # 测试成功
                    is_available = True
                    message = f'{provider_id} 连接测试通过'
                    logger.info(f"{provider_id} 测试成功: {data_count} 条数据, {latency_ms}ms")

                    result_data = {
                        'status': 'success',
                        'test_result': 'passed',
                        'available': is_available,
                        'message': message,
                        'details': {
                            'test_symbol': test_symbol,
                            'data_count': data_count,
                            'date_range': f'{start_date} to {end_date}',
                            'latency_ms': latency_ms
                        },
                        'timestamp': MarketTimeUtils.get_market_time_now(test_symbol).isoformat()
                    }

                    # 测试成功后，保存凭证到文件
                    if requires_auth and credentials:
                        BaseDataProvider.save_credentials(provider_id, credentials)
                        logger.info(f"{provider_id} 凭证已保存")

                    # 注意：不再保存测试状态到配置文件
                    # 状态由前端在内存中维护，下次启动时重新测试

                return jsonify(result_data)

            except Exception as e:
                logger.error(f"测试 {provider_id} 连接失败: {str(e)}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'测试连接时发生错误: {str(e)}',
                    'error_code': 'TEST_ERROR'
                }), 500

        @self.app.route('/api/v1/providers/<provider_id>/activate', methods=['POST'])
        def activate_provider(provider_id):
            """
            激活指定数据源（同时停用其他所有数据源）
            设计原则：同一时刻只能有一个活跃的数据源
            """
            try:
                config = self.config_manager.get('data_provider', {})
                providers = config.get('providers', [])

                # 查找目标数据源
                target_provider = None
                for p in providers:
                    if p.get('id') == provider_id or p.get('name') == provider_id:
                        target_provider = p
                        break

                if not target_provider:
                    return jsonify({
                        'status': 'error',
                        'message': f'数据源不存在: {provider_id}',
                        'error_code': 'PROVIDER_NOT_FOUND'
                    }), 404

                # 停用所有数据源
                for p in providers:
                    p['status'] = 'inactive'
                    p['updated_at'] = pd.Timestamp.now().isoformat()

                # 激活目标数据源
                target_provider['status'] = 'active'
                target_provider['updated_at'] = pd.Timestamp.now().isoformat()

                # 更新配置文件中的 primary_source
                config['primary_source'] = provider_id
                config['providers'] = providers
                self.config_manager.update({'data': config})

                logger.info(f"已激活数据源: {provider_id}，其他数据源已自动停用")

                return jsonify({
                    'status': 'success',
                    'message': f'已切换到 {target_provider.get("name", provider_id)}',
                    'active_provider': provider_id,
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"激活数据源失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'PROVIDER_ACTIVATE_FAILED'
                }), 500

        # ============================================================
        # 凭证管理端点（Credentials Management）
        # ============================================================

        @self.app.route('/api/v1/credentials', methods=['GET'])
        def get_credentials():
            """获取所有凭证列表（敏感信息脱敏）"""
            try:
                config = self.config_manager.get('credentials', {})
                credentials_list = []

                for key, cred in config.items():
                    # 脱敏处理
                    sanitized_cred = {
                        'id': key,
                        'type': cred.get('type', 'unknown'),
                        'provider': cred.get('provider', ''),
                        'username': cred.get('username', ''),
                        'api_key': '***' + cred.get('api_key', '')[-4:] if cred.get('api_key') else '',
                        'enabled': cred.get('enabled', True),
                        'created_at': cred.get('created_at', ''),
                        'updated_at': cred.get('updated_at', '')
                    }
                    credentials_list.append(sanitized_cred)

                return jsonify({
                    'status': 'success',
                    'credentials': credentials_list,
                    'total': len(credentials_list),
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"获取凭证列表失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIALS_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/credentials/<credential_id>', methods=['GET'])
        def get_credential(credential_id):
            """获取指定凭证（脱敏）"""
            try:
                config = self.config_manager.get('credentials', {})
                cred = config.get(credential_id)

                if not cred:
                    return jsonify({
                        'status': 'error',
                        'message': f'凭证不存在: {credential_id}',
                        'error_code': 'CREDENTIAL_NOT_FOUND'
                    }), 404

                # 脱敏处理
                sanitized_cred = {
                    'id': credential_id,
                    'type': cred.get('type', 'unknown'),
                    'provider': cred.get('provider', ''),
                    'username': cred.get('username', ''),
                    'api_key': '***' + cred.get('api_key', '')[-4:] if cred.get('api_key') else '',
                    'enabled': cred.get('enabled', True),
                    'created_at': cred.get('created_at', ''),
                    'updated_at': cred.get('updated_at', '')
                }

                return jsonify({
                    'status': 'success',
                    'credential': sanitized_cred,
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"获取凭证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIAL_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/credentials', methods=['POST'])
        def create_credential():
            """创建新凭证"""
            try:
                new_cred = request.get_json()
                if not new_cred:
                    return jsonify({
                        'status': 'error',
                        'message': '无效的凭证数据',
                        'error_code': 'INVALID_CREDENTIAL_DATA'
                    }), 400

                # 验证必填字段
                required_fields = ['id', 'type']
                for field in required_fields:
                    if field not in new_cred:
                        return jsonify({
                            'status': 'error',
                            'message': f'缺少必填字段: {field}',
                            'error_code': 'MISSING_REQUIRED_FIELD'
                        }), 400

                config = self.config_manager.get('credentials', {})

                # 检查是否已存在
                if new_cred['id'] in config:
                    return jsonify({
                        'status': 'error',
                        'message': f'凭证已存在: {new_cred["id"]}',
                        'error_code': 'CREDENTIAL_ALREADY_EXISTS'
                    }), 409

                # 添加默认字段
                new_cred.setdefault('enabled', True)
                new_cred.setdefault('created_at', pd.Timestamp.now().isoformat())

                config[new_cred['id']] = new_cred
                self.config_manager.update({'credentials': config})
                logger.info(f"创建凭证成功: {new_cred['id']}")

                # 返回脱敏数据
                sanitized = {
                    'id': new_cred['id'],
                    'type': new_cred.get('type'),
                    'provider': new_cred.get('provider', ''),
                    'enabled': new_cred.get('enabled', True)
                }

                return jsonify({
                    'status': 'success',
                    'message': '凭证创建成功',
                    'credential': sanitized,
                    'timestamp': pd.Timestamp.now().isoformat()
                }), 201
            except Exception as e:
                logger.error(f"创建凭证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIAL_CREATE_FAILED'
                }), 500

        @self.app.route('/api/v1/credentials/<credential_id>', methods=['PUT'])
        def update_credential(credential_id):
            """更新凭证"""
            try:
                updated_data = request.get_json()
                if not updated_data:
                    return jsonify({
                        'status': 'error',
                        'message': '无效的更新数据',
                        'error_code': 'INVALID_UPDATE_DATA'
                    }), 400

                config = self.config_manager.get('credentials', {})

                if credential_id not in config:
                    return jsonify({
                        'status': 'error',
                        'message': f'凭证不存在: {credential_id}',
                        'error_code': 'CREDENTIAL_NOT_FOUND'
                    }), 404

                # 更新字段
                config[credential_id].update(updated_data)
                config[credential_id]['updated_at'] = pd.Timestamp.now().isoformat()

                self.config_manager.update({'credentials': config})
                logger.info(f"更新凭证成功: {credential_id}")

                return jsonify({
                    'status': 'success',
                    'message': '凭证更新成功',
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"更新凭证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIAL_UPDATE_FAILED'
                }), 500

        @self.app.route('/api/v1/credentials/<credential_id>', methods=['DELETE'])
        def delete_credential(credential_id):
            """删除凭证"""
            try:
                config = self.config_manager.get('credentials', {})

                if credential_id not in config:
                    return jsonify({
                        'status': 'error',
                        'message': f'凭证不存在: {credential_id}',
                        'error_code': 'CREDENTIAL_NOT_FOUND'
                    }), 404

                del config[credential_id]
                self.config_manager.update({'credentials': config})
                logger.info(f"删除凭证成功: {credential_id}")

                return jsonify({
                    'status': 'success',
                    'message': '凭证删除成功',
                    'timestamp': pd.Timestamp.now().isoformat()
                })
            except Exception as e:
                logger.error(f"删除凭证失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'error_code': 'CREDENTIAL_DELETE_FAILED'
                }), 500

        @self.app.route('/api/v1/data/index-prices')
        def get_index_prices_api():
            """获取指数价格数据（直接来自当前数据提供者）"""
            try:
                symbol = request.args.get('symbol', type=str)
                start_date_str = request.args.get('start_date', type=str)
                end_date_str = request.args.get('end_date', type=str)
                if not all([symbol, start_date_str, end_date_str]):
                    return jsonify({'status': 'error', 'message': '缺少必要参数', 'error_code': 'MISSING_PARAMS'}), 400
                # 🔧 统一使用 pd.Timestamp，不使用字符串日期
                start_date = pd.to_datetime(start_date_str)
                end_date = pd.to_datetime(end_date_str)
                provider = self.provider_selector.select_provider_for_symbol(
                    symbol=symbol,
                    provider_factory=self.provider_factory
                )
                if not provider or not hasattr(provider, 'get_index_prices'):
                    return jsonify({'status': 'error', 'message': '数据提供者不可用',
                                    'error_code': 'DATA_PROVIDER_UNAVAILABLE'}), 503
                # 🔧 使用目标市场当前本地时间
                market_local_time = MarketTimeUtils.get_market_time_now(symbol)
                df = provider.get_index_prices(symbol, start_date, end_date, market_local_time)
                data = df.to_dict(orient='records') if hasattr(df, 'to_dict') else []
                return jsonify(
                    {'status': 'success', 'data': data, 'count': len(data), 'timestamp': pd.Timestamp.now().isoformat()})
            except Exception as e:
                logger.error(f"获取指数价格失败: {e}")
                return jsonify({'status': 'error', 'message': str(e), 'error_code': 'INDEX_PRICES_FETCH_FAILED'}), 500

        @self.app.route('/api/v1/data/index-returns')
        def get_index_returns_api():
            """获取指数收益率序列（排除异常日）"""
            try:
                symbol = request.args.get('symbol', type=str)
                start_date_str = request.args.get('start_date', type=str)
                end_date_str = request.args.get('end_date', type=str)
                if not all([symbol, start_date_str, end_date_str]):
                    return jsonify({'status': 'error', 'message': '缺少必要参数', 'error_code': 'MISSING_PARAMS'}), 400
                start_date =MarketTimeUtils.to_market_time_by_symbol(pd.to_datetime(start_date_str),symbol)
                end_date = MarketTimeUtils.to_market_time_by_symbol(pd.to_datetime(end_date_str),symbol)
                provider = self.provider_selector.select_provider_for_symbol(
                    symbol=symbol,
                    provider_factory=self.provider_factory
                )
                if not provider or not hasattr(provider, 'get_index_returns'):
                    return jsonify({'status': 'error', 'message': '数据提供者不可用',
                                    'error_code': 'DATA_PROVIDER_UNAVAILABLE'}), 503
                series = provider.get_index_returns(symbol, start_date, end_date)
                data = [{'date': str(idx), 'return': float(val)} for idx, val in
                        (series.items() if hasattr(series, 'items') else [])]
                # 使用目标市场时区的时间戳
                timestamp_with_tz = MarketTimeUtils.get_market_time_now(symbol)
                return jsonify(
                    {'status': 'success', 'data': data, 'count': len(data), 'timestamp': timestamp_with_tz.isoformat()})
            except Exception as e:
                logger.error(f"获取指数收益率失败: {e}")
                return jsonify({'status': 'error', 'message': str(e), 'error_code': 'INDEX_RETURNS_FETCH_FAILED'}), 500

        @self.app.route('/api/v1/data/event-window')
        def get_event_window_api():
            """获取事件窗口数据（窗口+基准期）"""
            try:
                symbol = request.args.get('symbol', type=str)
                event_date = request.args.get('event_date', type=str)
                event_type = request.args.get('event_type', default='market_crash', type=str)
                window_days = request.args.get('window_days', type=int)
                baseline_days = request.args.get('baseline_days', type=int)
                if not all([symbol, event_date]):
                    return jsonify({'status': 'error', 'message': '缺少必要参数', 'error_code': 'MISSING_PARAMS'}), 400

                # 选择数据提供者
                provider = self.provider_selector.select_provider_for_symbol(
                    symbol=symbol,
                    provider_factory=self.provider_factory
                )
                if not provider:
                    logger.error(f"数据提供者未找到: symbol={symbol}")
                    return jsonify({
                        'status': 'error',
                        'message': '数据提供者未初始化，请检查数据源配置（config/dev/data_provider_config.yml）',
                        'error_code': 'DATA_PROVIDER_NOT_FOUND',
                        'hint': '确保 primary_source 已配置且有效（如 tushare, yahoo, akshare）'
                    }), 503

                # 检查方法是否存在
                if not hasattr(provider, 'get_event_window_data'):
                    logger.error(f"provider 类型: {type(provider).__name__}, 方法: {dir(provider)}")
                    return jsonify({
                        'status': 'error',
                        'message': f'数据提供者（{type(provider).__name__}）不支持 get_event_window_data 方法',
                        'error_code': 'METHOD_NOT_SUPPORTED'
                    }), 503

                logger.info(
                    f"调用 get_event_window_data: symbol={symbol}, event_date={event_date}, event_type={event_type}")
                result = provider.get_event_window_data(symbol, event_date, event_type, window_days, baseline_days)
                # 仅返回统计信息与样本，避免过大payload
                event_records = result.get('event_window')
                baseline_records = result.get('baseline')
                event_data = event_records.head(200).to_dict(orient='records') if hasattr(event_records,
                                                                                          'to_dict') else []
                baseline_data = baseline_records.head(200).to_dict(orient='records') if hasattr(baseline_records,
                                                                                                'to_dict') else []
                # 使用目标市场时区的时间戳
                timestamp_with_tz = MarketTimeUtils.get_market_time_now(symbol)
                return jsonify({
                    'status': 'success',
                    'event_window': {'count': len(event_records) if hasattr(event_records, '__len__') else 0,
                                     'samples': event_data},
                    'baseline': {'count': len(baseline_records) if hasattr(baseline_records, '__len__') else 0,
                                 'samples': baseline_data},
                    'config': result.get('config', {}),
                    'timestamp': timestamp_with_tz.isoformat()
                })
            except Exception as e:
                logger.error(f"获取事件窗口数据失败: {e}")
                return jsonify({'status': 'error', 'message': str(e), 'error_code': 'EVENT_WINDOW_FETCH_FAILED'}), 500

        # 新增：K线数据（周期切换 + 最近30周期 + 事件标注 + 无限滚动支持）
        @self.app.route('/api/v1/data/kline')
        def get_kline_data():
            try:
                symbol = request.args.get('symbol', type=str)
                period = request.args.get('period', default='daily', type=str)
                count = request.args.get('count', default=30, type=int)
                before_str = request.args.get('before', type=str)  # 新增：获取此日期之前的数据
                before = None
                if before_str:
                    before = pd.Timestamp(before_str)
                    before = MarketTimeUtils.to_market_time_by_symbol(before,symbol)
                    
                if not symbol:
                    return jsonify({'status': 'error', 'message': '缺少index_id', 'error_code': 'MISSING_PARAMS'}), 400
                    
                # 走真实数据源路径
                provider = self.provider_selector.select_provider_for_symbol(
                    symbol=symbol,
                    provider_factory=self.provider_factory
                )
                if not provider or not hasattr(provider, 'get_index_prices'):
                    # 生产环境：数据提供者不可用时返回错误，不降级为Mock
                    return jsonify({'status': 'error', 'message': '数据提供者不可用',
                                    'error_code': 'DATA_PROVIDER_UNAVAILABLE'}), 503

                try:
                    multiplier = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(period, 1)
                    days_needed = count * multiplier * 2

                    # 🔧 统一使用 pd.Timestamp，不转换为字符串
                    if before:
                        end_date = before
                    else:
                        # 🔧 获取目标市场当前时间
                        end_date = MarketTimeUtils.get_market_time_now(symbol)

                    start_date = end_date - pd.Timedelta(days=days_needed)
                    
                    # ✅ 使用目标市场当前本地时间
                    market_local_time = MarketTimeUtils.get_market_time_now(symbol)
                    df = provider.get_index_prices(symbol, start_date, end_date, market_local_time, period=period)
                    if hasattr(df, 'empty') and df.empty:
                        # 生产环境：真实数据为空时返回错误
                        return jsonify({'status': 'error', 'message': '无数据', 'error_code': 'NO_DATA'}), 404
                except Exception as e:
                    logger.error(f"获取真实数据失败: {e}")
                    # 生产环境：获取数据失败时返回错误
                    return jsonify({'status': 'error', 'message': f'数据获取失败: {str(e)}',
                                    'error_code': 'DATA_FETCH_FAILED'}), 500

                # 处理真实数据：补齐OHLC、周期转换、事件检测
                # 补齐OHLC
                # TODO：待清理
                if 'open' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
                    df = df.copy()
                    df['open'] = df['close'].shift(1).fillna(df['close'])
                    df['high'] = df['close'] * 1.005
                    df['low'] = df['close'] * 0.995

                # 周期转换已由数据层统一处理（缓存 + _convert_period），此处无需再重算
                df2 = df.tail(count)

                # 事件检测（最小规则）
                # TODO：待清理
                try:
                    df2['pct_change'] = df2['close'].pct_change() * 100
                    events = []
                    for i in range(len(df2)):
                        chg = float(df2.loc[df2.index[i], 'pct_change']) if not pd.isna(
                            df2.loc[df2.index[i], 'pct_change']) else 0.0
                        dt = df2.loc[df2.index[i], 'date']
                        cl = float(df2.loc[df2.index[i], 'close'])
                        if chg <= -5.0:
                            events.append({'date': dt.strftime('%Y-%m-%d'), 'type': 'market_crash',
                                           'title': f'暴跌 {abs(chg):.2f}%', 'decline_pct': chg, 'price': cl,
                                           'impact': 'negative', 'severity': 'high' if chg > -7 else 'critical'})
                        elif chg >= 5.0:
                            events.append(
                                {'date': dt.strftime('%Y-%m-%d'), 'type': 'rally', 'title': f'暴涨 {chg:.2f}%',
                                 'rise_pct': chg, 'price': cl, 'impact': 'positive', 'severity': 'high'})
                except Exception:
                    events = []

                # 转换为dict并处理NaN值（替换为null以确保JSON有效）
                data = df2.to_dict(orient='records')
                # 将所有NaN替换为None（JSON序列化时会变成null）
                for record in data:
                    for key, value in record.items():
                        if pd.isna(value):
                            record[key] = None
                        elif key == 'date' and hasattr(value, 'strftime'):
                            record[key] = value.strftime('%Y-%m-%d')
                # 使用目标市场时区的时间戳
                timestamp_with_tz = MarketTimeUtils.get_market_time_now(symbol)
                return jsonify(
                    {'status': 'success', 'data': data, 'period': period, 'count': len(data), 'events': events,
                     'timestamp': timestamp_with_tz.isoformat()})
            except Exception as e:
                logger.error(f"获取K线数据失败: {e}")
                return jsonify({'status': 'error', 'message': str(e), 'error_code': 'KLINE_FETCH_FAILED'}), 500

        # 真实模式端点
        @self.app.route('/api/v1/data/kline/realtime', methods=['GET'])
        def get_realtime_kline():
            """
            获取实时K线柱数据（真实模式，支持日线/周线/月线）
            
            🆕 新逻辑：
            - 日线：返回独立的当天K柱
            - 周线/月线：返回合并后的周期K柱（如果当天不是新周/新月，则合并到最后一个周期）
            
            参数：
                symbol: 证券代码（必需）
                period: 周期（daily/weekly/monthly，默认 daily）
            
            返回：
                {
                    status: 'success',
                    data: {
                        date: 'YYYY-MM-DD',  # 周线/月线为周期开始日期
                        open: float,
                        high: float,
                        low: float,
                        close: float,
                        volume: int,
                        should_poll: bool  # 服务器根据 trading_phase 决定，前端只依赖此字段控制行为
                    },
                    timestamp: str
                }
            """
            try:
                symbol = request.args.get('symbol', type=str)
                period = request.args.get('period', default='daily', type=str)  # 🆕 新增：周期参数
                
                if not symbol:
                    return jsonify({'status': 'error', 'message': '缺少index_id', 'error_code': 'MISSING_PARAMS'}), 400
                
                if period not in ['daily', 'weekly', 'monthly']:
                    return jsonify({'status': 'error', 'message': f'无效的period: {period}', 'error_code': 'INVALID_PERIOD'}), 400

                provider = self.provider_selector.select_provider_for_symbol(
                    symbol=symbol,
                    provider_factory=self.provider_factory
                )
                if not provider:
                    return jsonify({'status': 'error', 'message': '数据提供者不可用',
                                    'error_code': 'DATA_PROVIDER_UNAVAILABLE'}), 503

                try:
                    result = provider.get_realtime_kline(symbol, period, provider)
                    # 使用目标市场时区的时间戳
                    timestamp_with_tz = MarketTimeUtils.get_market_time_now(symbol)
                    return jsonify({
                        'status': 'success',
                        'data': result,
                        'timestamp': timestamp_with_tz.isoformat()
                    })

                except Exception as e:
                    logger.error(f"获取实时K线失败: {e}", exc_info=True)
                    return jsonify(
                        {'status': 'error', 'message': str(e), 'error_code': 'REALTIME_KLINE_FETCH_FAILED'}), 500

            except Exception as e:
                logger.error(f"处理实时K线请求失败: {e}", exc_info=True)
                return jsonify(
                    {'status': 'error', 'message': str(e), 'error_code': 'REALTIME_KLINE_REQUEST_FAILED'}), 500


        # ============================================================
        # 错误处理中间件
        # ============================================================
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'status': 'error',
                'message': '端点不存在',
                'error_code': 'ENDPOINT_NOT_FOUND'
            }), 404

        @self.app.errorhandler(405)
        def method_not_allowed(error):
            return jsonify({
                'status': 'error',
                'message': '方法不允许',
                'error_code': 'METHOD_NOT_ALLOWED'
            }), 405

        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({
                'status': 'error',
                'message': '内部服务器错误',
                'error_code': 'INTERNAL_SERVER_ERROR'
            }), 500

    def _register_mock_routes(self):
        """注册Mock API路由 - 从 api_service_mock.py 导入"""
        from app.api_service_mock import register_mock_routes
        
        # 将Mock路由注册到当前 Flask app
        register_mock_routes(self.app)
        logger.info("🎭 Mock API路由已注册")

    def start_api_service(self, host: str = '0.0.0.0', port: int = 8080):
        """启动API服务"""
        try:
            logger.info(f"启动市场数据API服务: http://{host}:{port}")

            # 配置Flask应用
            self.app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            self.app.config['JSON_SORT_KEYS'] = False
            self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

            # 添加中间件
            self._add_middleware()

            # 启动服务
            self.app.run(
                host=host,
                port=port,
                debug=False,
                threaded=True,
                use_reloader=False
            )

        except Exception as e:
            logger.error(f"API服务启动失败: {e}")
            raise

    def _add_middleware(self):
        """添加中间件"""

        # 请求日志中间件
        @self.app.before_request
        def log_request():
            if request.path != '/health':
                logger.info(f"API请求: {request.method} {request.path} - {request.remote_addr}")

        # 响应处理中间件
        @self.app.after_request
        def after_request(response):
            response.headers['X-Market-Data-API'] = 'DeepSeekQuant/1.0.0'
            response.headers['X-Response-Time'] = '100ms'  # 示例值
            return response

        # 错误处理中间件
        @self.app.errorhandler(Exception)
        def handle_exception(e):
            logger.error(f"API处理异常: {e}")
            return jsonify({
                'status': 'error',
                'message': '内部服务器错误',
                'error_code': 'INTERNAL_ERROR'
            }), 500

    def _setup_socketio_handlers(self):
        """设置Socket.IO事件处理器 - 实时推送支持"""

        @self.socketio.on('connect')
        def handle_connect():
            """客户端连接事件"""
            logger.info("Socket.IO客户端已连接")
            emit('connection_response', {
                'status': 'connected',
                'message': '已连接到市场数据服务',
                'timestamp': pd.Timestamp.now().isoformat()
            })

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """客户端断开连接事件"""
            logger.info("Socket.IO客户端已断开")

    def stop_api_service(self):
        """停止API服务"""
        logger.info("停止市场数据API服务")
        # 这里实现优雅关闭逻辑

    def get_api_statistics(self) -> Dict[str, Any]:
        """获取API统计信息"""
        return {
            'total_requests': 0,  # 需要实际实现请求计数
            'successful_requests': 0,
            'failed_requests': 0,
            'average_response_time': 0.0,
            'endpoint_usage': {},
            'error_rates': {},
            'timestamp': pd.Timestamp.now().isoformat()
        }

    def export_api_logs(self, filepath: str) -> bool:
        """导出API日志"""
        try:
            # 实现API日志导出逻辑
            return True
        except Exception as e:
            logger.error(f"API日志导出失败: {e}")
            return False

    def cleanup(self):
        """清理资源"""
        self.stop_api_service()
        logger.info("API服务清理完成")