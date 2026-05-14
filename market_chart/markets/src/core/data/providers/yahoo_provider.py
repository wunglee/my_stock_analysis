"""
Yahoo Finance数据提供者 - 整合版
实现HistoricalDataProvider接口

职责：
- 通过yfinance API获取全球市场历史数据
- 支持指数、个股、波动率等多种数据类型
- 数据标准化和质量验证
- 实现统一的HistoricalDataProvider接口
- 代理配置和会话管理

Note: 
- 反爬虫和请求限流逻辑由 yfinance_patch 处理
- YahooFinanceDataProvider 仅负责代理配置和会话创建
- 避免在两个地方重复实现相同的反爬虫逻辑

依赖：
pip install yfinance

优势：
- 全球市场覆盖广泛
- 免费使用（有速率限制）
- 数据质量较高
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

import pandas as pd
import yfinance as yf
from core.data.providers.base_provider import BaseDataProvider
# 导入新的数据结构
from core.data.providers.protocols import (PriceData, IntradayData, IntradayTickRecord,
                                                  OrderBookLevel)
# 导入 HTTP/2 补丁
from core.data.providers.yfinance_patch import patch_yfinance, _CURL_SESSION
from core.share.market.market_time_utils import MarketTimeUtils
from core.share.market.market_utils import MarketUtils

logger = logging.getLogger('YahooFinanceDataProvider')


@dataclass
class YahooFinanceConfig:
    """Yahoo Finance配置数据类"""
    test_symbol: str = "^GSPC"  # 默认测试符号
    timeout: int = 30  # 请求超时（秒）
    max_retries: int = 3  # 最大重试次数


class YahooFinanceDataProvider(BaseDataProvider):
    """Yahoo Finance数据提供者"""

    def __init__(self):
        """
        初始化Yahoo Finance数据提供者
        
        Note:
            proxy 从配置文件读取，不通过参数传递
        """
        super().__init__()
        self.initialize()

    def initialize(self, **kwargs):
        # 延迟导入yfinance（避免环境依赖问题）
        try:
            import yfinance as yf
            self.yf = yf
            try:
                # 从 ConfigManager 读取 providers 配置
                provider_config = self.config_manager.get_provider_config()
                # 查找 yahoo provider 的 use_proxy 配置
                use_proxy = False
                for provider in provider_config.providers:
                    if provider.get('id') == "yahoo":
                        use_proxy = provider.get('use_proxy', False)
                        break
                import os
                proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
                if not use_proxy:
                    logger.info("🚫 yahoo配置为不使用代理，将使用无代理的网络请求")
                    # 不再清除环境变量，而是通过自定义会话控制代理
                    self.proxy = None
                    logger.info("✅ Yahoo 代理已禁用（通过自定义会话）")
                else:
                    # 查找可用的代理设置
                    for var in proxy_vars:
                        if var in os.environ:
                            self.proxy = os.environ[var]
                            logger.info(f"✅ 使用代理: {var} = {self.proxy}")
                            break
                    else:
                        self.proxy = None
                        logger.info("🌐 未找到代理环境变量，将使用直连")
                    if self.proxy:
                        logger.info("✅ Yahoo 代理已设置")
                    else:
                        logger.info("🌐 Yahoo 配置为使用直连")
            except Exception as e:
                logger.warning(f"配置代理时出错: {e}，将使用默认设置")

            patch_yfinance(proxy_url=self.proxy)
            logger.info("✅ YahooFinanceDataProvider initialized with Browser Simulation patch (anti-429)")
        except ImportError:
            logger.error("yfinance not installed. Please run: pip install yfinance")
            self.yf = None
            self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize yfinance: {e}")
            self.yf = None
            self.available = False

    def get_test_symbol(self) -> str:
        """获取测试符号"""
        return "^GSPC.US"  # 标普500指数

    def _fetch_history_kline_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp,
                                               period: str = 'daily') -> PriceData:
        """
        从 Yahoo Finance API 获取数据（实现基类抽象方法）
        
        💚 此方法由 BaseDataProvider._get_with_cache() 调用
        💚 三层缓存逻辑在基类中已实现，子类只需实现外部API调用
        
        Args:
            symbol: 证券代码（如 "^GSPC", "AAPL"）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: 周期 ('daily', 'weekly', 'monthly')
        
        Returns:
            PriceData: 标准化的价格数据
        """
        if self.yf is None:
            raise RuntimeError("yfinance not available")

        logger.info(f"Fetching stock data for {symbol} from {start_date} to {end_date}, period={period}")
        # 使用带重试机制的方法获取数据
        if self.yf is None:
            raise RuntimeError("yfinance not available")

        try:
            # Note: 请求限流和重试逻辑由 yfinance_patch 处理
            # 统一只取日线，周期转换由基类 _fetch_from_external_api 统一处理
            # Note: yfinance_patch 补丁会拦截所有 yfinance 内部请求
            ticker_obj = self.yf.Ticker(self._map_to_yahoo(symbol), session=_CURL_SESSION)
            start_date = MarketTimeUtils.to_market_time_by_symbol(start_date, symbol)
            end_date = MarketTimeUtils.to_market_time_by_symbol(end_date, symbol)
            data = ticker_obj.history(start=start_date, end=end_date, interval='1d')
        except Exception as e:
            logger.warning(f"Yahoo API调用失败 {symbol}: {e}")
            raise
        # 检查数据是否有效
        if data is None or data.empty:
            standardized_data = MarketUtils.standardize_format_to_price_data(data, symbol)
            logger.info(f"Yahoo 返回空数据：{symbol}")
            return standardized_data
        else:
            try:
                standardized_data = MarketUtils.standardize_format_to_price_data(data, symbol)
                logger.info(f"Successfully fetched {len(standardized_data.records)} records for {symbol}")
                return standardized_data
            except Exception as e:
                logger.error(f"Failed to standardized data for {symbol}: {e}")
                raise ValueError(f"Failed to standardized data for {symbol}: {str(e)}")

    def _fetch_real_intraday_from_external_api(self, symbol: str, start_time_str: str,
                                               end_time_str: str) -> pd.DataFrame:
        """
        从数据源获取分时数据（子类必须实现）

        Args:
            symbol: 证券代码
            start_time_str: 开始时间
            end_time_str: 结束时间

        Returns:
            pd.DataFrame: 分时数据 DataFrame
        """
        logger.info(f"时间范围: {start_time_str} ~ {end_time_str}")

        # 使用 yfinance 获取 1分钟数据
        # Note: yfinance_patch 补丁会拦截所有 yfinance 内部请求
        ticker_obj = self.yf.Ticker(self._map_to_yahoo(symbol), session=_CURL_SESSION)

        # Yahoo Finance 的 1m 数据最多只能获取 7 天
        # 如果时间范围超过 7 天，使用 5m 数据
        start_time = pd.Timestamp(start_time_str)
        end_time = pd.Timestamp(end_time_str)
        time_diff = (start_time - end_time).days
        if time_diff > 7:
            interval = '5m'
            period = '7d'  # 5分钟数据最多7天
            logger.info("时间范围超过 1 天，使用 5分钟数据")
        else:
            interval = '1m'
            period = '1d'  # 1分钟数据最多1天
            logger.info("使用 1分钟数据")

        # 获取数据
        df = ticker_obj.history(period=period, interval=interval)

        if df is None or df.empty:
            logger.warning(f"⚠️ Yahoo Finance 返回空数据: {symbol}")
            return df
        start_time = MarketTimeUtils.to_market_time_by_symbol(start_time, symbol)
        end_time = MarketTimeUtils.to_market_time_by_symbol(end_time, symbol)
        df = df[(df.index >= start_time) & (df.index <= end_time)]
        return df

    def _map_to_yahoo(self, symbol: str) -> str:
        """
        将应用内部代码映射到 Yahoo Finance 格式
        
        规则：
        - 后缀：.SH（上海）、.SZ（深圳）、.HK（香港）、.US（美国）、.JP（日本）、.SG（新加坡）
        - 前缀：^ 表示指数，否则为股票
        
        映射逻辑：
        1. 移除市场后缀（.SH、.SZ、.HK、.US、.JP、.SG）
        2. 对于指数（^前缀），转换为 Yahoo Finance 格式
        3. 对于股票，根据市场添加对应后缀
        
        示例：
        - A股指数：^000001.SH → ^000001.SS, ^399001.SZ → ^399001.SZ
        - A股个股：600000.SH → 600000.SS, 000001.SZ → 000001.SZ
        - 港股指数：^HSI.HK → ^HSI
        - 港股个股：00700.HK → 0700.HK
        - 美股指数：^GSPC.US → ^GSPC
        - 美股个股：AAPL.US → AAPL
        - 日股指数：^N225.JP → ^N225
        - 日股个股：9984.JP → 9984.T
        - 新加股指数：^STI.SG → ^STI
        - 新加股个股：D05.SG → D05.SI
        
        Args:
            symbol: 应用内部代码格式
            
        Returns:
            str: Yahoo Finance 格式的代码
        """
        # 检查是否为指数（^前缀）
        is_index = symbol.startswith('^')

        # 提取基础代码（移除^前缀和市场后缀）
        base_symbol = symbol
        if is_index:
            base_symbol = base_symbol[1:]  # 移除^前缀

        # 移除市场后缀
        market_suffixes = ['.SH', '.SZ', '.HK', '.US','.EU', '.JP', '.SG']
        for suffix in market_suffixes:
            if base_symbol.endswith(suffix):
                base_symbol = base_symbol[:-len(suffix)]
                break

        # 根据市场和指数类型进行映射
        if symbol.endswith('.SH'):
            # 上海市场：指数和股票都添加.SS后缀
            if is_index:
                return f'{base_symbol}.SS'
            else:
                return f'{base_symbol}.SS'

        elif symbol.endswith('.SZ'):
            # 深圳市场：指数和股票都添加.SZ后缀
            if is_index:
                return f'{base_symbol}.SZ'
            else:
                return f'{base_symbol}.SZ'

        elif symbol.endswith('.HK'):
            # 香港市场：指数保持^前缀，股票添加.HK后缀
            if is_index:
                return f'^{base_symbol}'
            else:
                # 港股代码需要移除前导0（如00700 → 0700）
                if base_symbol.startswith('00') and len(base_symbol) > 1:
                    base_symbol = base_symbol.lstrip('0')
                return f'{base_symbol}.HK'
        elif symbol.endswith('.EU'):
            # 欧洲市场：指数保持^前缀，股票直接使用
            if is_index:
                return f'^{base_symbol}'
            else:
                return base_symbol
        elif symbol.endswith('.US'):
            # 美国市场：指数保持^前缀，股票直接使用
            if is_index:
                return f'^{base_symbol}'
            else:
                return base_symbol

        elif symbol.endswith('.JP'):
            # 日本市场：指数保持^前缀，股票添加.T后缀
            if is_index:
                return f'^{base_symbol}'
            else:
                return f'{base_symbol}.T'

        elif symbol.endswith('.SG'):
            # 新加坡市场：指数保持^前缀，股票添加.SI后缀
            if is_index:
                return f'^{base_symbol}'
            else:
                return f'{base_symbol}.SI'

        else:
            # 默认情况：直接返回原代码（可能是已经符合Yahoo格式的代码）
            return symbol

    def _to_IntradayData(self, df: pd.DataFrame, symbol: str, trade_date: pd.Timestamp,
                         interpolate_func=None) -> IntradayData:
        """
        将 Yahoo Finance 的 DataFrame 转换为 IntradayData
        
        Args:
            df: Yahoo Finance 返回的 DataFrame（index 为时间戳）
            symbol: 证券代码
            trade_date: 交易日期
        
        Returns:
            IntradayData: 分时数据对象
        """

        is_index = MarketUtils.is_index(symbol)

        # 获取昨收价（使用第一个开盘价作为近似值）
        yesterday_close = float(df['Open'].iloc[0]) if not df.empty else 0.0

        # 获取当前价格（最后一条数据的收盘价）
        current_price = float(df['Close'].iloc[-1]) if not df.empty else 0.0

        # 计算涨跌
        change = current_price - yesterday_close
        change_percent = (change / yesterday_close * 100) if yesterday_close > 0 else 0.0

        # 转换 ticks
        ticks = []
        total_volume = 0
        total_amount = 0.0

        for idx, row in df.iterrows():
            price = float(row['Close'])
            volume = int(row['Volume']) if pd.notna(row['Volume']) else 0

            total_volume += volume
            total_amount += price * volume
            avg_price = total_amount / total_volume if total_volume > 0 else price

            # 将时间索引转换为当地时间的H:M:S格式
            if hasattr(idx, 'strftime'):
                time_str = idx.strftime('%H:%M:%S')
            elif hasattr(idx, 'time'):
                time_str = str(idx.time())
            else:
                time_str = str(idx)

            ticks.append(IntradayTickRecord(
                time=time_str,
                price=round(price, 2),
                volume=volume,
                avg_price=round(avg_price, 2)
            ))

        return IntradayData(
            symbol=symbol,
            name=symbol,  # Yahoo Finance 不提供中文名称
            current_price=round(current_price, 2),
            yesterday_close=round(yesterday_close, 2),
            change=round(change, 2),
            change_percent=round(change_percent, 2),
            ticks=ticks,
            order_book_bids=[],  # 由调用方设置
            order_book_asks=[],  # 由调用方设置
            trade_records=[],  # 由调用方设置
            trade_date=trade_date,
            order_book_message='',  # 由调用方设置
            trade_records_message='',  # 由调用方设置
            is_index=is_index,
            should_poll=False
        )

    def _fetch_realtime_order_book_from_external_api(self, symbol: str) -> Optional[tuple[list, list]]:
        """
        获取实时盘口数据（买卖五档）

        Args:
            symbol: 证券代码（带后缀，如000300.SH）

        Returns:
            (order_book_bids, order_book_asks): 买盘列表, 卖盘列表

        注意：
        - 只在交易时间内调用此方法
        - 非交易时间返回空列表
        """
        # 获取实时盘口数据（一档买卖盘）
        is_index = MarketUtils.is_index(symbol)
        order_book_bids = []
        order_book_asks = []
        if not is_index:
            try:
                ticker = yf.Ticker(self._map_to_yahoo(symbol), session=_CURL_SESSION)
                if not ticker.info:
                    logger.info(f"⚠️ Yahoo 返回空的盘口数据：{symbol}")
                else:
                    info = ticker.info
                    bid_price = info.get('bid')
                    ask_price = info.get('ask')
                    bid_size = info.get('bidSize')
                    ask_size = info.get('askSize')

                    if bid_price and bid_size:
                        order_book_bids.append(OrderBookLevel(
                            price=round(float(bid_price), 2),
                            volume=int(bid_size)
                        ))

                    if ask_price and ask_size:
                        order_book_asks.append(OrderBookLevel(
                            price=round(float(ask_price), 2),
                            volume=int(ask_size)
                        ))

                    logger.debug(
                        f"📊 Yahoo Finance 盘口: {symbol} bid={bid_price}x{bid_size} ask={ask_price}x{ask_size}")
            except Exception as e:
                logger.warning(f"⚠️ 获取 Yahoo Finance 盘口数据失败: {symbol}, {e}")
            return order_book_bids, order_book_asks
        else:
            return [], []

    def _fetch_realtime_trade_records_from_external_api(self, symbol: str):
        """
        获取实时成交明细（逐笔成交）

        Args:
            symbol: 证券代码（带后缀，如000300.SH）

        Returns:
            trade_records: 成交明细列表

        注意：
        - 只在交易时间内调用此方法
        - 非交易时间返回空列表
        """
        # Yahoo Finance API不提供逐笔成交数据，返回空列表
        logger.info(f"⚠️ Yahoo Finance 不支持逐笔成交数据: {symbol}")
        return []

    # _standardize_format method has been moved to MarketUtils.standardize_format_to_price_data

    # validate_data_quality方法已迁移到data_quality_utils.py
    # 请使用: from core.data.quality.data_quality_utils import validate_data_quality
    
    def get_complete_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取指定股票的完整基本面数据（Yahoo Finance实现）
        
        Args:
            symbol: 股票代码（带市场后缀，如 'AAPL.US'）
        
        Returns:
            Dict[str, Any]: 完整的基本面数据字典
        """
        try:
            logger.info(f"Fetching fundamental data for {symbol}")
            
            # 转换为Yahoo格式
            yahoo_symbol = self._map_to_yahoo(symbol)
            
            # 获取股票信息
            ticker = self.yf.Ticker(yahoo_symbol)
            info = ticker.info
            
            if not info:
                logger.warning(f"No fundamental data found for {symbol}")
                return {}
            
            # 构建基本面数据字典
            fundamental_data = {
                # 基本信息
                'symbol': symbol,
                'name': info.get('longName', info.get('shortName', symbol)),
                'markets': symbol.split('.')[-1] if '.' in symbol else 'US',
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
                'currency': info.get('currency', ''),
                'exchange': info.get('exchange', ''),
                
                # 估值指标
                'pe': info.get('trailingPE'),
                'pb': info.get('priceToBook'),
                'ps': info.get('priceToSalesTrailing12Months'),
                'pcf': None,  # Yahoo 不提供直接的PCF
                'peg': info.get('pegRatio'),
                'enterprise_value': info.get('enterpriseValue'),
                'ev_to_revenue': info.get('enterpriseToRevenue'),
                'ev_to_ebitda': info.get('enterpriseToEbitda'),
                
                # 盈利能力
                'roe': info.get('returnOnEquity'),
                'roic': None,  # Yahoo 不提供直接的ROIC
                'roa': info.get('returnOnAssets'),
                'gross_margin': info.get('grossMargins'),
                'operating_margin': info.get('operatingMargins'),
                'net_margin': info.get('profitMargins'),
                'ebitda_margin': None,  # 需要计算
                
                # 成长性
                'revenue_growth': info.get('revenueGrowth'),
                'profit_growth': info.get('earningsGrowth'),
                'ocf_growth': None,  # Yahoo 不提供OCF增长率
                'earnings_growth_qtr': info.get('earningsQuarterlyGrowth'),
                'revenue_growth_qtr': None,  # 需要额外获取
                
                # 资产质量
                '资产负债率': None,  # 需要计算
                '流动比率': info.get('currentRatio'),
                'quick_ratio': info.get('quickRatio'),
                'debt_to_equity': info.get('debtToEquity'),
                'total_debt': info.get('totalDebt'),
                'total_assets': info.get('totalAssets'),
                'total_liabilities': None,  # 需要计算
                'current_assets': info.get('totalAssets'),  # 近似
                'current_liabilities': info.get('totalDebt'),  # 近似
                'book_value': info.get('bookValue'),
                'intangible_assets': None,  # 需要额外获取
                '商誉占比': None,  # 需要额外获取
                '应收账款占比': None,  # 需要额外获取
                
                # 流动性
                'market_cap': info.get('marketCap'),
                'shares_outstanding': info.get('sharesOutstanding'),
                'float_shares': info.get('floatShares'),
                'avg_volume': info.get('averageVolume'),
                'avg_volume_10d': info.get('averageVolume10days'),
                'avg_volume_3m': info.get('averageDailyVolume3Month'),
                'current_price': info.get('currentPrice'),
                'previous_close': info.get('previousClose'),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
                
                # 现金流
                'operating_cash_flow': info.get('operatingCashflow'),
                'free_cash_flow': info.get('freeCashflow'),
                'capital_expenditure': None,  # 需要额外获取
                'cash_and_equivalents': info.get('totalCash'),
                'cash_per_share': info.get('totalCashPerShare'),
                
                # 分红和股东回报
                'dividend_yield': info.get('dividendYield'),
                'dividend_rate': info.get('dividendRate'),
                'payout_ratio': info.get('payoutRatio'),
                'ex_dividend_date': info.get('exDividendDate'),
                'beta': info.get('beta'),
                
                # 分析师预期
                'target_high_price': info.get('targetHighPrice'),
                'target_low_price': info.get('targetLowPrice'),
                'target_mean_price': info.get('targetMeanPrice'),
                'recommendation_mean': info.get('recommendationMean'),
                'recommendation_key': info.get('recommendationKey'),
                'number_of_analyst_opinions': info.get('numberOfAnalystOpinions'),
                
                # 盈利数据
                'earnings_ttm': info.get('trailingEps'),
                'earnings_forward': info.get('forwardEps'),
                'pe_forward': info.get('forwardPE'),
                'revenue_ttm': info.get('totalRevenue'),
                'revenue_per_share': info.get('revenuePerShare'),
                'earnings_date': info.get('earningsDate'),
            }
            
            # 计算一些衍生指标
            self._calculate_yahoo_derived_metrics(fundamental_data)
            
            logger.info(f"✓ Successfully fetched fundamental data for {symbol}")
            return fundamental_data
            
        except Exception as e:
            logger.error(f"Failed to fetch fundamental data for {symbol}: {e}")
            raise ValueError(f"Failed to fetch fundamental data for {symbol}: {str(e)}") from e
    
    def _calculate_yahoo_derived_metrics(self, data: Dict[str, Any]) -> None:
        """计算Yahoo Finance的衍生指标"""
        # 计算资产负债率
        if data['total_assets'] is not None and data['total_debt'] is not None and data['total_assets'] > 0:
            data['资产负债率'] = data['total_debt'] / data['total_assets']
        
        # 计算EBITDA Margin
        if data['ev_to_ebitda'] is not None and data['ev_to_revenue'] is not None and data['ev_to_ebitda'] > 0:
            data['ebitda_margin'] = data['ev_to_revenue'] / data['ev_to_ebitda']
        
        # 计算OCF增长率（需要历史数据，这里无法计算）
        data['ocf_growth'] = None
        
        # 计算应收账款占比（需要额外数据，这里无法计算）
        data['应收账款占比'] = None
        
        # 计算商誉占比（需要额外数据，这里无法计算）
        data['商誉占比'] = None
        
        # 计算ROIC的近似值（如果ROIC不存在）
        if data['roic'] is None and data['roa'] is not None and data['资产负债率'] is not None:
            # 简化的ROIC估算：ROA / (1 - 资产负债率)
            if data['资产负债率'] < 1:
                data['roic'] = data['roa'] / (1 - data['资产负债率'])