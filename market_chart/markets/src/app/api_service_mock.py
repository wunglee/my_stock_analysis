"""数据质量Mock API服务 - 提供模拟数据REST API接口

[应用层] Mock数据专用API服务
状态: ✅ Mock数据端点独立服务
创建时间: 2025-12-21
版本: 1.0

Mock API端点:
- GET  /api/v1/chart/data/mock     - 获取模拟图表数据（K线+技术指标+事件）
- GET  /api/v1/intraday/mock       - 获取模拟分时图数据

架构说明:
- 完全独立于真实数据API服务
- 专注于Mock数据生成和返回
- 支持不同交易时段模拟
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

from app.chart_data import ChartDataAssembler
from core.data.providers.mock_provider import MockDataProvider
from core.data.providers.protocols import TickRange
from core.share import MarketCode
from core.share.market import MarketUtils
from core.share.market.market_enums import TradingPhase
from core.share.market.market_time_utils import MarketTimeUtils
from core.signal.indicator_service import TechnicalIndicators
from tests.fixtures.core.data.mock_historical_data_provider import MockHistoricalDataProvider
logger = logging.getLogger('App.MockAPIService')


class DataQualityMockAPIService:
    """数据质量Mock API服务 - 提供模拟数据RESTful API接口
    
    架构说明:
    - 应用层：Mock API路由和请求处理
    - 使用MockDataProvider生成模拟数据
    - 职责分离：与真实数据API完全独立
    """

    def __init__(self):
        
        self.app = Flask(__name__)
        
        # 启用CORS
        CORS(self.app)
        
        self._setup_routes()

    def _setup_routes(self):
        """设置Mock API路由"""
        
        @self.app.route('/api/v1/chart/data/mock', methods=['GET'])
        def get_chart_data_mock():
            """获取合并的图表数据（K线+技术指标+事件）【模拟数据】
            
            查询参数：
                - symbol: 股票/指数代码（必需）
                - period: 周期（daily/weekly/monthly，默认 daily）
                - count: 数据条数（默认 120）
                - before: 获取此日期之前的数据（YYYY-MM-DD，已获取的K线日期，市场本地时间，可选）
                - indicators: 需要的指标，逗号分隔（默认 'all'）
                               支持: vol, macd, rsi, kdj, obv
                - trading_phase: 交易时段（before_open/trading/noon_break/after_close，默认 trading）
            
            返回示例：
            {
                "status": "success",
                "data": {
                    "kline": [...],
                    "indicators": {...},
                    "events": [...],
                    "needs_realtime_kline": true/false
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
                        before = pd.Timestamp(before_str)  # 直接使用，不转换时区
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

                # 使用Mock数据源
                logger.info(f"🎭 使用模拟数据源: {symbol}")
                mock_provider = MockDataProvider()

                # 🎭 从前端获取trading_phase参数（用于needs_realtime_kline判断）
                trading_phase_str = request.args.get('trading_phase', 'trading')  # 默认盘中
                try:
                    trading_phase = TradingPhase.parse(trading_phase_str)
                    mock_provider.set_mock_trading_phase(trading_phase)
                    logger.info(f"🎭 Mock模式 - trading_phase={trading_phase.name}")
                except KeyError:
                    logger.warning(f"🎭 无效的trading_phase: {trading_phase_str}，使用默认TRADING")
                    mock_provider.set_mock_trading_phase(TradingPhase.TRADING)

                # 创建指标服务
                indicator_service = TechnicalIndicators(market=MarketCode.CN, timeframe=period)
                chart_assembler = ChartDataAssembler(
                    data_provider=mock_provider,
                    indicator_service=indicator_service
                )

                current_time = pd.Timestamp.now()
                
                # 调用组装器
                chart_data = chart_assembler.assemble_chart_data(
                    symbol=symbol,
                    period=period,
                    count=count,
                    before=before,
                    indicators=indicators,
                    market_local_time=current_time
                )

                return jsonify({
                    'status': 'success',
                    'data': chart_data,
                    'metadata': {
                        'symbol': symbol,
                        'period': period,
                        'count': len(chart_data.get('kline', [])),
                        'indicators': list(chart_data.get('indicators', {}).keys()),
                        'events_count': len(chart_data.get('events', [])),
                        'data_source': 'mock'
                    },
                    'timestamp': pd.Timestamp.now().isoformat()
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
                logger.error(f"获取Mock图表数据失败: {e}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'获取图表数据失败: {str(e)}',
                    'error_code': 'CHART_DATA_FETCH_FAILED'
                }), 500

        @self.app.route('/api/v1/intraday/mock', methods=['GET'])
        def get_intraday_mock():
            """获取模拟分时图数据
            
            查询参数：
                - symbol: 证券代码（必需）
                - trading_phase: 交易时段（'trading'/'before_open'/'after_close'，必需）- 模拟场景由前端按钮控制
                - tick_range: TickRange JSON（可选）
                - last_price: 上次请求的最终价格，用于保证价格连续性（可选）
            
            🔧 注意：服务器根据 trading_phase 决定返回 should_poll，前端只依赖 should_poll 控制行为
            """
            try:
                symbol = request.args.get('symbol')
                if not symbol:
                    return jsonify({
                        'status': 'error',
                        'message': '缺少必需参数: symbol',
                        'error_code': 'MISSING_PARAMETER'
                    }), 400

                trading_phase_str = request.args.get('trading_phase')
                if not trading_phase_str:
                    return jsonify({
                        'status': 'error',
                        'message': '缺少必需参数: trading_phase',
                        'error_code': 'MISSING_PARAMETER'
                    }), 400

                # 验证 trading_phase
                valid_modes = ['trading', 'before_open', 'after_close']
                if trading_phase_str not in valid_modes:
                    return jsonify({
                        'status': 'error',
                        'message': f'trading_phase必须是{valid_modes}之一',
                        'error_code': 'INVALID_TRADING_PHASE'
                    }), 400

                # 转换为枚举
                trading_phase = TradingPhase.parse(trading_phase_str)

                # 解析 last_price
                last_price_str = request.args.get('last_price')
                last_price = None
                if last_price_str:
                    try:
                        last_price = float(last_price_str)
                    except ValueError:
                        return jsonify({
                            'status': 'error',
                            'message': f'last_price必须是数字: {last_price_str}',
                            'error_code': 'INVALID_LAST_PRICE'
                        }), 400

                # 解析 tick_range
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
                            start_time=pd.Timestamp(tick_range_dict['start_time']),
                            end_time=pd.Timestamp(tick_range_dict['end_time']),
                            period_seconds=int(tick_range_dict['period_seconds'])
                        )
                    except (json.JSONDecodeError, ValueError) as e:
                        return jsonify({
                            'status': 'error',
                            'message': f'解析tick_range失败: {str(e)}',
                            'error_code': 'INVALID_TICK_RANGE_FORMAT'
                        }), 400

                logger.info(
                    f"🎮 模拟模式: symbol={symbol}, trading_phase={trading_phase_str}(前端按钮控制), tick_range={'已提供' if tick_range else '未提供'}")

                # 直接调用 MockDataProvider
                generator = MockDataProvider()

                # 判断是否为指数
                is_index = symbol in ['000001.SH', '000300.SH', '399001.SZ', '399006.SZ']

                # 🔧 API层统一使用UTC时间，然后转换为市场本地时间
                utc_now = pd.Timestamp.now(tz='UTC')
                market_code = MarketUtils.infer_market_from_symbol(symbol)
                market_tz = MarketTimeUtils.get_market_timezone(market_code)
                trade_date = utc_now.tz_convert(market_tz)

                # tick_range 由前端直接传入，不需要转换

                mock_data = generator.generate_intraday_data(
                    symbol=symbol,
                    trade_date=trade_date,
                    tick_range=tick_range,
                    trading_phase=trading_phase,
                    last_price=last_price,
                    is_index=is_index
                )

                # 转换为前端需要的格式
                intraday_data = {
                    'symbol': mock_data.symbol,
                    'name': mock_data.name,
                    'current_price': mock_data.current_price,
                    'yesterday_close': mock_data.yesterday_close,
                    'change': mock_data.change,
                    'change_percent': mock_data.change_percent,
                    'times': [tick.time for tick in mock_data.ticks],
                    'prices': [tick.price for tick in mock_data.ticks],
                    'volumes': [tick.volume for tick in mock_data.ticks],
                    'avg_prices': [tick.avg_price for tick in mock_data.ticks],
                    'order_book': {
                        'bids': [{'price': level.price, 'volume': level.volume} for level in mock_data.order_book_bids],
                        'asks': [{'price': level.price, 'volume': level.volume} for level in mock_data.order_book_asks],
                        'message': mock_data.order_book_message
                    },
                    'trade_records': {
                        'items': [{'time': t.time, 'price': t.price, 'volume': t.volume, 'type': t.direction} for t in
                                  mock_data.trade_records],
                        'message': mock_data.trade_records_message
                    },
                    'is_index': mock_data.is_index,
                    'should_poll': mock_data.should_poll  # 🔧 服务器根据 trading_phase 决定，前端只依赖此字段控制行为
                }

                return jsonify({
                    'status': 'success',
                    'data': intraday_data,
                    'timestamp': pd.Timestamp.now().isoformat()
                })

            except Exception as e:
                logger.error(f"获取模拟分时数据失败: {e}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'获取模拟分时数据失败: {str(e)}',
                    'error_code': 'INTRADAY_MOCK_FAILED'
                }), 500

        @self.app.route('/api/v1/data/kline/mock', methods=['GET'])
        def get_kline_data_mock():
            """获取K线数据【模拟数据】
            
            查询参数：
                - symbol: 股票/指数代码（必需）
                - period: 周期（daily/weekly/monthly，默认 daily）
                - count: 数据条数（默认 30）
                - before: 获取此日期之前的数据（YYYY-MM-DD，已获取的K线日期，市场本地时间，可选）
            
            返回示例：
            {
                "status": "success",
                "data": [...],  # K线数据
                "events": [...],  # 事件数据
                "period": "daily",
                "count": 30
            }
            """
            try:
                symbol = request.args.get('symbol')
                if not symbol:
                    return jsonify({'status': 'error', 'message': '缺少index_id', 'error_code': 'MISSING_PARAMS'}), 400

                period = request.args.get('period', default='daily', type=str)
                count = request.args.get('count', default=30, type=int)
                before_str = request.args.get('before', type=str)  # K线日期（市场本地时间）
                
                # 🔧 before 是已获取的K线日期，本身就是市场本地时间，无需时区转换
                before = None
                if before_str:
                    try:
                        before = pd.Timestamp(before_str)  # 直接使用，不转换时区
                    except Exception as e:
                        return jsonify({
                            'status': 'error',
                            'message': f'无效的日期格式: {str(e)}',
                            'error_code': 'INVALID_DATE_FORMAT'
                        }), 400

                # 使用 MockHistoricalDataProvider 生成逼真的K线数据
                mock_provider = MockHistoricalDataProvider()

                # 计算日期范围
                multiplier = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(period, 1)
                days_needed = count * multiplier * 2
                
                # 🔧 API层统一使用UTC时间
                if before:
                    end_date = before
                else:
                    end_date = pd.Timestamp.now()
                    
                start_date = end_date - pd.Timedelta(days=days_needed)

                # 获取原始日线数据
                # ✅ 直接传递 pd.Timestamp 对象，不转换为字符串
                current_time = pd.Timestamp.now()
                df = mock_provider.get_index_prices(
                    symbol, 
                    start_date,
                    end_date, 
                    current_time
                )
                
                if hasattr(df, 'empty') and df.empty:
                    return jsonify({'status': 'error', 'message': '无数据', 'error_code': 'NO_DATA'}), 404

                # 补齐OHLC（基于close生成逼真的OHLC）
                df = df.copy()
                if 'open' not in df.columns:
                    df['open'] = df['close'].shift(1).fillna(df['close'])
                if 'high' not in df.columns or 'low' not in df.columns:
                    # 基于收益率波动生成high/low
                    returns = df['close'].pct_change().fillna(0)
                    volatility = returns.rolling(5, min_periods=1).std().fillna(0.01)
                    df['high'] = df['close'] * (1 + volatility * np.random.uniform(0.3, 0.8, len(df)))
                    df['low'] = df['close'] * (1 - volatility * np.random.uniform(0.3, 0.8, len(df)))
                    # 确保 high >= close >= low 和 high >= open >= low
                    df['high'] = df[['high', 'close', 'open']].max(axis=1)
                    df['low'] = df[['low', 'close', 'open']].min(axis=1)

                # 周期转换
                df2 = df.copy()
                df2['date'] = pd.to_datetime(df2['date'])
                df2 = df2.set_index('date')
                if period == 'weekly':
                    df2 = df2.resample('W').agg(
                        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
                elif period == 'monthly':
                    df2 = df2.resample('M').agg(
                        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
                df2 = df2.reset_index()
                df2 = df2.tail(count)

                # 事件检测（最小规则）
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

                # 转换为dict并处理NaN值（替换为null以确保JSON有效）
                data = df2.to_dict(orient='records')
                for record in data:
                    for key, value in record.items():
                        if pd.isna(value):
                            record[key] = None
                        elif key == 'date' and hasattr(value, 'strftime'):
                            record[key] = value.strftime('%Y-%m-%d')
                            
                return jsonify({
                    'status': 'success', 
                    'data': data, 
                    'period': period, 
                    'count': len(data), 
                    'events': events,
                    'timestamp': pd.Timestamp.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"模拟K线数据生成失败: {e}")
                return jsonify({'status': 'error', 'message': str(e), 'error_code': 'MOCK_KLINE_FAILED'}), 500

        @self.app.route('/api/v1/data/kline/realtime/mock', methods=['GET'])
        def get_realtime_kline_mock():
            """
            获取当天K线柱的实时数据【模拟模式】
            
            参数：
                symbol: 证券代码
                trading_phase: 交易时段 (before_open, trading, after_close) - 用于模拟控制
                trade_date: 交易日期 (YYYY-MM-DD，浏览器本地时间)，默认今天
                client_timezone: 浏览器时区（如 'Asia/Shanghai'，必需如果提供trade_date）
                is_index: 是否为指数，默认false
            
            返回：
                {
                    status: 'success',
                    data: {
                        date: 'YYYY-MM-DD',
                        open: float,
                        high: float,
                        low: float,
                        close: float,
                        volume: int,
                        trading_phase: str,
                        should_poll: bool
                    },
                    timestamp: str
                }
            """
            try:
                symbol = request.args.get('symbol', type=str)
                if not symbol:
                    return jsonify({'status': 'error', 'message': '缺少index_id', 'error_code': 'MISSING_PARAMS'}), 400

                # 🔧 获取前端传入的trading_phase参数（用于模拟控制）
                trading_phase_str = request.args.get('trading_phase', 'trading')  # 默认盘中
                try:
                    trading_phase = TradingPhase.parse(trading_phase_str)
                except KeyError:
                    return jsonify({
                        'status': 'error',
                        'message': f'无效的trading_phase: {trading_phase_str}，允许值: before_open, trading, after_close',
                        'error_code': 'INVALID_TRADING_PHASE'
                    }), 400

                trade_date_str = request.args.get('trade_date')
                client_timezone = request.args.get('client_timezone')
                
                # 🔧 API层统一使用UTC时间，然后转换为市场本地时间
                if not trade_date_str:
                    # 没有提供日期，使用服务器UTC时间
                    utc_now = pd.Timestamp.now(tz='UTC')
                    market_code = MarketUtils.infer_market_from_symbol(symbol)
                    market_tz = MarketTimeUtils.get_market_timezone(market_code)
                    trade_date = utc_now.tz_convert(market_tz)
                else:
                    # 提供了日期，需要从浏览器本地时间转换
                    if not client_timezone:
                        return jsonify({
                            'status': 'error',
                            'message': '提供trade_date参数时必须同时提供client_timezone参数',
                            'error_code': 'MISSING_CLIENT_TIMEZONE'
                        }), 400
                    try:
                        # 使用统一的转换方法
                        market_code = MarketUtils.infer_market_from_symbol(symbol)
                        trade_date = pd.Timestamp(trade_date_str)
                        trade_date = MarketTimeUtils.to_market_time(trade_date,  market_code)
                    except ValueError as e:
                        return jsonify({
                            'status': 'error',
                            'message': str(e),
                            'error_code': 'INVALID_TIMEZONE_OR_DATE'
                        }), 400
                    
                is_index_str = request.args.get('is_index', 'false').lower()
                is_index = is_index_str in ['true', '1', 'yes']

                # 🔧 调用领域层，显式传入参数
                provider = MockDataProvider()
                result = provider.get_realtime_kline(
                    symbol=symbol,
                    trade_date=trade_date,
                    trading_phase=trading_phase,
                    is_index=is_index
                )

                return jsonify({
                    'status': 'success',
                    'data': result,
                    'timestamp': pd.Timestamp.now().isoformat()
                })

            except Exception as e:
                logger.error(f"处理模拟实时K线请求失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'status': 'error', 'message': str(e), 'error_code': 'MOCK_REALTIME_KLINE_FAILED'}), 500

    def run(self, host: str = '0.0.0.0', port: int = 5002, debug: bool = False):
        """启动Mock API服务
        
        Args:
            host: 监听地址
            port: 监听端口（默认5002，与真实API的5001区分）
            debug: 调试模式
        """
        logger.info(f"🎭 Mock API服务启动: http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


def register_mock_routes(app: Flask):
    """将Mock路由注册到指定的Flask应用
    
    Args:
        app: Flask应用实例
        
    注意：此函数用于将Mock路由注册到主API服务，避免启动独立服务
    """
    from core.data.providers.mock_provider import MockDataProvider
    from core.share.market.market_enums import TradingPhase
    from core.share import MarketCode
    from app.chart_data import ChartDataAssembler
    from core.signal.indicator_service import TechnicalIndicators
    
    @app.route('/api/v1/chart/data/mock', methods=['GET'])
    def get_chart_data_mock():
        """获取合并的图表数据（K线+技术指标+事件）【模拟数据】"""
        try:
            symbol = request.args.get('symbol')
            if not symbol:
                return jsonify({'status': 'error', 'message': '缺少必需参数: symbol', 'error_code': 'MISSING_PARAMETER'}), 400

            period = request.args.get('period', 'daily')
            count = request.args.get('count', 120, type=int)
            before_str = request.args.get('before')
            before = pd.to_datetime(before_str) if before_str else None
            indicators = request.args.get('indicators', 'all')

            if period not in ['daily', 'weekly', 'monthly']:
                return jsonify({'status': 'error', 'message': f'无效的周期参数: {period}', 'error_code': 'INVALID_PERIOD'}), 400
            if count <= 0 or count > 1000:
                return jsonify({'status': 'error', 'message': f'数据条数必须在 1-1000 之间', 'error_code': 'INVALID_COUNT'}), 400

            logger.info(f"🎭 使用模拟数据源: {symbol}")
            mock_provider = MockDataProvider()
            trading_phase_str = request.args.get('trading_phase', 'trading')
            try:
                trading_phase = TradingPhase.parse(trading_phase_str)
                mock_provider.set_mock_trading_phase(trading_phase)
            except KeyError:
                mock_provider.set_mock_trading_phase(TradingPhase.trading)

            indicator_service = TechnicalIndicators(market=MarketCode.CN, timeframe=period)
            chart_assembler = ChartDataAssembler(data_provider=mock_provider, indicator_service=indicator_service)
            chart_data = chart_assembler.assemble_chart_data(symbol=symbol, period=period, count=count, before=before, indicators=indicators, market_local_time=pd.Timestamp.now())

            return jsonify({'status': 'success', 'data': chart_data, 'metadata': {'symbol': symbol, 'period': period, 'count': len(chart_data.get('kline', [])), 'indicators': list(chart_data.get('indicators', {}).keys()), 'events_count': len(chart_data.get('events', [])), 'data_source': 'mock'}, 'timestamp': pd.Timestamp.now().isoformat()})
        except Exception as e:
            logger.error(f"获取Mock图表数据失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': f'获取图表数据失败: {str(e)}', 'error_code': 'CHART_DATA_FETCH_FAILED'}), 500

    @app.route('/api/v1/intraday/mock', methods=['GET'])
    def get_intraday_mock():
        """获取模拟分时图数据"""
        try:
            symbol = request.args.get('symbol')
            if not symbol:
                return jsonify({'status': 'error', 'message': '缺少必需参数: symbol', 'error_code': 'MISSING_PARAMETER'}), 400
            trading_phase_str = request.args.get('trading_phase')
            if not trading_phase_str:
                return jsonify({'status': 'error', 'message': '缺少必需参数: trading_phase', 'error_code': 'MISSING_PARAMETER'}), 400
            valid_modes = ['trading', 'before_open', 'after_close']
            if trading_phase_str not in valid_modes:
                return jsonify({'status': 'error', 'message': f'trading_phase必须是{valid_modes}之一', 'error_code': 'INVALID_TRADING_PHASE'}), 400

            trading_phase = TradingPhase.parse(trading_phase_str)
            last_price_str = request.args.get('last_price')
            last_price = float(last_price_str) if last_price_str else None

            import json
            tick_range_str = request.args.get('tick_range')
            tick_range = None
            if tick_range_str:
                tick_range_dict = json.loads(tick_range_str)
                from core.data.providers.protocols import TickRange
                tick_range = TickRange(start_time=pd.Timestamp(tick_range_dict['start_time']), end_time=pd.Timestamp(tick_range_dict['end_time']), period_seconds=int(tick_range_dict['period_seconds']))

            generator = MockDataProvider()
            is_index = symbol in ['000001.SH', '000300.SH', '399001.SZ', '399006.SZ']
            # 🔧 获取目标市场当前时间
            trade_date = MarketTimeUtils.get_market_time_now(symbol)
            mock_data = generator.generate_intraday_data(symbol=symbol, trade_date=trade_date, tick_range=tick_range, trading_phase=trading_phase, last_price=last_price, is_index=is_index)

            intraday_data = {
                'symbol': mock_data.symbol, 'name': mock_data.name, 'current_price': mock_data.current_price,
                'yesterday_close': mock_data.yesterday_close, 'change': mock_data.change, 'change_percent': mock_data.change_percent,
                'times': [tick.time for tick in mock_data.ticks], 'prices': [tick.price for tick in mock_data.ticks],
                'volumes': [tick.volume for tick in mock_data.ticks], 'avg_prices': [tick.avg_price for tick in mock_data.ticks],
                'order_book': {'bids': [{'price': level.price, 'volume': level.volume} for level in mock_data.order_book_bids], 'asks': [{'price': level.price, 'volume': level.volume} for level in mock_data.order_book_asks], 'message': mock_data.order_book_message},
                'trade_records': {'items': [{'time': t.time, 'price': t.price, 'volume': t.volume, 'type': t.direction} for t in mock_data.trade_records], 'message': mock_data.trade_records_message},
                'is_index': mock_data.is_index, 'should_poll': mock_data.should_poll
            }
            return jsonify({'status': 'success', 'data': intraday_data, 'timestamp': pd.Timestamp.now().isoformat()})
        except Exception as e:
            logger.error(f"获取模拟分时数据失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': f'获取模拟分时数据失败: {str(e)}', 'error_code': 'INTRADAY_MOCK_FAILED'}), 500

    @app.route('/api/v1/data/kline/mock', methods=['GET'])
    def get_kline_data_mock():
        """获取K线数据【模拟数据】"""
        try:
            symbol = request.args.get('symbol')
            if not symbol:
                return jsonify({'status': 'error', 'message': '缺少index_id', 'error_code': 'MISSING_PARAMS'}), 400
            period = request.args.get('period', default='daily', type=str)
            count = request.args.get('count', default=30, type=int)
            before_str = request.args.get('before', type=str)
            before = pd.Timestamp(before_str) if before_str else None

            from tests.fixtures.core.data.mock_historical_data_provider import MockHistoricalDataProvider
            import numpy as np
            mock_provider = MockHistoricalDataProvider()
            multiplier = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(period, 1)
            days_needed = count * multiplier * 2
            # 🔧 end_date: K线日期或目标市场时间
            if before:
                end_date = before  # K线日期，不需转换
            else:
                # 获取目标市场当前时间
                end_date = MarketTimeUtils.get_market_time_now(symbol)
            start_date = end_date - pd.Timedelta(days=days_needed)
            # 使用目标市场当前本地时间
            market_local_time = MarketTimeUtils.get_market_time_now(symbol)
            df = mock_provider.get_index_prices(symbol, start_date, end_date, market_local_time)
            if hasattr(df, 'empty') and df.empty:
                return jsonify({'status': 'error', 'message': '无数据', 'error_code': 'NO_DATA'}), 404

            df = df.copy()
            if 'open' not in df.columns:
                df['open'] = df['close'].shift(1).fillna(df['close'])
            if 'high' not in df.columns or 'low' not in df.columns:
                returns = df['close'].pct_change().fillna(0)
                volatility = returns.rolling(5, min_periods=1).std().fillna(0.01)
                df['high'] = df['close'] * (1 + volatility * np.random.uniform(0.3, 0.8, len(df)))
                df['low'] = df['close'] * (1 - volatility * np.random.uniform(0.3, 0.8, len(df)))
                df['high'] = df[['high', 'close', 'open']].max(axis=1)
                df['low'] = df[['low', 'close', 'open']].min(axis=1)

            df2 = df.copy()
            df2['date'] = pd.to_datetime(df2['date'])
            df2 = df2.set_index('date')
            if period == 'weekly':
                df2 = df2.resample('W').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
            elif period == 'monthly':
                df2 = df2.resample('M').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
            df2 = df2.reset_index().tail(count)

            df2['pct_change'] = df2['close'].pct_change() * 100
            events = []
            for i in range(len(df2)):
                chg = float(df2.loc[df2.index[i], 'pct_change']) if not pd.isna(df2.loc[df2.index[i], 'pct_change']) else 0.0
                dt = df2.loc[df2.index[i], 'date']
                cl = float(df2.loc[df2.index[i], 'close'])
                if chg <= -5.0:
                    events.append({'date': dt.strftime('%Y-%m-%d'), 'type': 'market_crash', 'title': f'暴跌 {abs(chg):.2f}%', 'decline_pct': chg, 'price': cl, 'impact': 'negative', 'severity': 'high' if chg > -7 else 'critical'})
                elif chg >= 5.0:
                    events.append({'date': dt.strftime('%Y-%m-%d'), 'type': 'rally', 'title': f'暴涨 {chg:.2f}%', 'rise_pct': chg, 'price': cl, 'impact': 'positive', 'severity': 'high'})

            data = df2.to_dict(orient='records')
            for record in data:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
                    elif key == 'date' and hasattr(value, 'strftime'):
                        record[key] = value.strftime('%Y-%m-%d')
            return jsonify({'status': 'success', 'data': data, 'period': period, 'count': len(data), 'events': events, 'timestamp': pd.Timestamp.now().isoformat()})
        except Exception as e:
            logger.error(f"模拟K线数据生成失败: {e}")
            return jsonify({'status': 'error', 'message': str(e), 'error_code': 'MOCK_KLINE_FAILED'}), 500

    @app.route('/api/v1/data/kline/realtime/mock', methods=['GET'])
    def get_realtime_kline_mock():
        """获取当天K线柱的实时数据【模拟模式】"""
        try:
            symbol = request.args.get('symbol', type=str)
            if not symbol:
                return jsonify({'status': 'error', 'message': '缺少index_id', 'error_code': 'MISSING_PARAMS'}), 400
            trading_phase_str = request.args.get('trading_phase', 'trading')
            try:
                trading_phase = TradingPhase.parse(trading_phase_str)
            except KeyError:
                return jsonify({'status': 'error', 'message': f'无效的trading_phase: {trading_phase_str}', 'error_code': 'INVALID_TRADING_PHASE'}), 400
            trade_date = request.args.get('trade_date')
            # 🔧 如果没有提供 trade_date，获取目标市场当前时间
            if not trade_date:
                trade_date = MarketTimeUtils.get_market_time_now(symbol)
            else:
                trade_date = pd.to_datetime(trade_date)
                
            is_index_str = request.args.get('is_index', 'false').lower()
            is_index = is_index_str in ['true', '1', 'yes']

            provider = MockDataProvider()
            result = provider.get_realtime_kline(symbol=symbol, trade_date=trade_date, trading_phase=trading_phase, is_index=is_index)
            return jsonify({'status': 'success', 'data': result, 'timestamp': pd.Timestamp.now().isoformat()})
        except Exception as e:
            logger.error(f"处理模拟实时K线请求失败: {e}")
            return jsonify({'status': 'error', 'message': str(e), 'error_code': 'MOCK_REALTIME_KLINE_FAILED'}), 500
    
    logger.info("🎭 Mock路由已注册到主API服务")
