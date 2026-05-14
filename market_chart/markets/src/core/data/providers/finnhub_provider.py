"""
Finnhub数据提供者 - 全球金融市场数据
实现HistoricalDataProvider接口

职责：
- 通过Finnhub API获取全球金融市场数据
- 支持股票、指数、外汇、加密货币
- 数据标准化和质量验证
- 实现统一的HistoricalDataProvider接口

依赖：
pip install finnhub-python

优势：
- 免费版60次/分钟（最高限额）
- 全球市场覆盖
- 实时和历史数据
- 财经新闻和社交情绪分析

配置：
- 需要API Key（从 https://finnhub.io/ 注册获取）
- 环境变量：FINNHUB_API_KEY
- 或通过credentials.yml配置
"""

import logging
import time
from typing import Optional

import finnhub
import pandas as pd

from core.data.providers.base_provider import BaseDataProvider
from core.data.providers.protocols import HistoricalDataProvider, PriceData
from core.share.config_manager import ConfigManager
from core.share.market.market_time_utils import MarketTimeUtils

logger = logging.getLogger(__name__)


class FinnhubDataProvider(BaseDataProvider, HistoricalDataProvider):
    """
    基于Finnhub的数据提供者
    
    支持多市场数据获取：
    - 美股：个股、指数
    - 全球股市：欧洲、亚洲等
    - 外汇、加密货币
    
    设计特点：
    - API Key认证
    - 速率限制管理（60次/分钟）
    - 统一的数据标准化接口
    - 透明失败原则（API问题直接抛出异常）
    """

    def __init__(self):
        """
        初始化Finnhub数据提供者
        
        Note:
            - API Key 从配置文件读取（credentials.yml）
            - proxy 从配置文件读取，不通过参数传递
            - 💚 不再使用 os.environ，统一使用 ConfigManager
        """
        # 💚 调用基类构造函数（初始化缓存）
        super().__init__()
        
        # 💚 从配置文件读取 API Key（不再使用环境变量）
        api_key = self._load_api_key_from_config()
        
        # 从配置文件中获取proxy
        config_manager = ConfigManager()
        proxy_config = config_manager.get_proxies_from_config()
        if proxy_config:
            # 使用HTTP代理（如果有配置的话）
            self.proxy = proxy_config.get('http') or proxy_config.get('socks5')
        else:
            self.proxy = None
        
        if api_key:
            self.client = finnhub.Client(api_key=api_key)
        else:
            self.client = None
            
        self._last_request_time = 0
        self._min_request_interval = 1.0  # 最小请求间隔（秒），60次/分钟
    
    def initialize(self,credential:str,**kwargs):
        """
        初始化客户端
        
        Args:
            **kwargs: 其他初始化参数
        """
        if credential:
            self.client = finnhub.Client(api_key=credential)
            logger.info(f"Finnhub客户端初始化成功: {credential[:8]}...")
        else:
            logger.warning("未提供API Key，无法初始化Finnhub客户端")

    def _load_api_key_from_config(self) -> Optional[str]:
        """
        从配置文件加载API Key
        
        Returns:
            API Key字符串，如果未找到则返回None
        """
        try:
            # 使用基类方法获取配置路径
            config_path = self._get_config_path('credentials.yml')
            
            # 检查配置文件是否存在
            if not config_path.exists():
                logger.debug("凭证配置文件不存在")
                return None
            
            # 读取配置文件
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                credentials_data = yaml.safe_load(f) or {}
            
            # 获取Finnhub的API Key
            finnhub_creds = credentials_data.get('finnhub', {})
            api_key = finnhub_creds.get('api_key')
            
            if api_key:
                logger.debug("从配置文件加载Finnhub API Key成功")
                return api_key
            else:
                logger.debug("配置文件中未找到Finnhub API Key")
                return None
                
        except Exception as e:
            logger.warning(f"从配置文件加载API Key失败: {e}")
            return None

    def get_test_symbol(self) -> str:
        """获取测试符号"""
        return 'AAPL'  # 苹果股票

    def _rate_limit_wait(self):
        """速率限制等待"""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        if time_since_last_request < self._min_request_interval:
            wait_time = self._min_request_interval - time_since_last_request
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            time.sleep(wait_time)
        
        self._last_request_time = time.time()

    def _normalize_symbol(self, symbol: str) -> str:
        """
        标准化股票代码为Finnhub格式
        
        Args:
            symbol: 原始股票代码
            
        Returns:
            Finnhub标准格式的股票代码
        """
        # Finnhub使用标准格式，例如：
        # - 美股：AAPL, TSLA
        # - 指数：^GSPC 转为 SPX
        
        symbol_mapping = {
            '^GSPC': 'SPX',  # 标普500
            '^DJI': 'DJI',   # 道琼斯
            '^IXIC': 'IXIC',  # 纳斯达克
        }
        
        normalized = symbol_mapping.get(symbol, symbol)
        
        # 去掉市场后缀（如果有）
        if '.' in normalized:
            base_symbol = normalized.split('.')[0]
            return base_symbol
        
        return normalized

    def get_index_prices(
        self,
        symbol: str,
        start_date:pd.Timestamp,
        end_date: pd.Timestamp,
        market_local_time: pd.Timestamp,
        period: str = 'daily'
    ) -> PriceData:
        """
        获取指数历史价格数据
        
        Args:
            symbol: 指数代码
            start_date: 开始日期 pd.Timestamp对象
            end_date: 结束日期 pd.Timestamp对象
            market_local_time: 目标市场当前本地时间（不带时区信息）
            period: 周期
        Returns:
            PriceData: 包含标准OHLCV数据的结构化对象
        """
        # 允许测试时即使没有有效凭证也能继续执行
        # 直到真正调用API时才会失败
        
        try:
            # 转换日期格式
            if isinstance(start_date, str):
                start_dt = pd.to_datetime(start_date)
            else:
                start_dt = start_date
            
            if isinstance(end_date, str):
                end_dt = pd.to_datetime(end_date)
            else:
                end_dt = end_date
            
            # Finnhub API需要Unix时间戳
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            # 标准化股票代码
            symbol = self._normalize_symbol(symbol)
            
            logger.info(f"Fetching Finnhub data for {symbol} ({symbol}) from {start_date} to {end_date}")
            
            # 速率限制
            self._rate_limit_wait()

            # 检查是否有API Key
            if not self.client:
                raise ValueError("Finnhub API密钥未配置")

            # 调用Finnhub API获取K线数据
            # resolution: 1, 5, 15, 30, 60, D, W, M
            candles = self.client.stock_candles(symbol, 'D', start_ts, end_ts)
            
            if not candles or candles.get('s') != 'ok':
                raise ValueError(f"Finnhub未返回{symbol}的数据，状态: {candles.get('s') if candles else 'None'}")
            
            # 转换为DataFrame
            df = pd.DataFrame({
                'date': pd.to_datetime(candles['t'], unit='s'),
                'open': candles['o'],
                'high': candles['h'],
                'low': candles['l'],
                'close': candles['c'],
                'volume': candles['v']
            })
            
            if df.empty:
                raise ValueError(f"Finnhub返回空数据: {symbol}")
            
            # 按日期排序
            df = df.sort_values('date').reset_index(drop=True)
            
            logger.info(f"Successfully fetched {len(df)} rows for {symbol}")
            
            # 返回PriceData对象
            price_data = PriceData.from_dataframe(df, symbol)
            self.set_needs_realtime_kline(price_data, market_local_time)
            return price_data
            
        except Exception as e:
            # 不重新抛出RuntimeError，保持异常类型一致性
            error_msg = str(e)
            
            # 特殊处理 403 错误 - Finnhub 免费版不支持历史数据
            if '403' in error_msg or "You don't have access" in error_msg:
                friendly_msg = (
                    f"Finnhub 免费版不支持历史K线数据 ({symbol})。"
                    "免费账户只能访问实时报价和公司信息。"
                    "如需历史数据，请使用 AKShare 或 Yahoo Finance。"
                )
                logger.warning(friendly_msg)
                raise ValueError(friendly_msg)
            
            if isinstance(e, ValueError):
                # 如果已经是ValueError，直接重新抛出
                logger.error(f"Finnhub获取数据失败 ({symbol}): {e}")
                raise
            else:
                # 其他异常包装为ValueError
                logger.error(f"Finnhub获取数据失败 ({symbol}): {e}")
                raise ValueError(f"Failed to fetch data for {symbol}: {e}")

    def get_index_returns(
        self,
        symbol: str,
        start_date:pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        获取指数收益率序列
        
        Args:
            symbol: 指数代码
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            Series with date index and return values
        """
        price_data = self.get_index_prices(symbol, start_date, end_date, MarketTimeUtils.get_market_time_now(symbol))
        df = price_data.to_dataframe().set_index('date')
        returns = df['close'].pct_change().dropna()
        return returns

    def get_stock_prices(
        self,
        stock_id: str,
        start_date:pd.Timestamp,
        end_date: pd.Timestamp,
        market_local_time: pd.Timestamp,
        period: str = 'daily'
    ) -> PriceData:
        """
        获取个股价格数据
        
        💚 注意: 此方法由基类处理缓存，不需覆写
        
        Args:
            stock_id: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            market_local_time: 目标市场当前本地时间（不带时区信息）
            period: 周期
        Returns:
            PriceData: 包含标准OHLCV数据的结构化对象
        """
        # 💚 由基类自动处理缓存
        return super().get_stock_prices(stock_id, start_date, end_date, market_local_time, period)
    
    def _fetch_history_kline_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str = 'daily') -> PriceData:
        """
        从 Finnhub API 获取数据（实现基类抽象方法）
        
        💚 注意:
        - 此方法仅供内部使用
        - 外部调用者应使用 get_index_prices()
        - 基类已自动处理缓存
        
        Args:
            symbol: 股票/指数代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: 周期 ('daily', 'weekly', 'monthly')
        
        Returns:
            PriceData: 价格数据对象
        """
        # 获取日线数据（Finnhub API 只返回日线）
        market_local_time = MarketTimeUtils.get_market_time_now(symbol)
        price_data = self.get_index_prices(symbol, start_date, end_date, market_local_time)
        
        return price_data

    def get_quote(self, symbol: str) -> dict:
        """
        获取实时报价（Finnhub独有功能）
        
        Args:
            symbol: 股票代码
        
        Returns:
            包含实时报价信息的字典
        """
        # 允许测试时即使没有有效凭证也能继续执行
        # 直到真正调用API时才会失败
        
        try:
            # 检查是否有API Key
            if not self.client:
                raise ValueError("Finnhub API密钥未配置，请设置FINNHUB_API_KEY环境变量或传入api_key参数")
            
            self._rate_limit_wait()
            symbol_normalized = self._normalize_symbol(symbol)
            quote = self.client.quote(symbol_normalized)
            
            return {
                'symbol': symbol,
                'current_price': quote.get('c'),
                'change': quote.get('d'),
                'percent_change': quote.get('dp'),
                'high': quote.get('h'),
                'low': quote.get('l'),
                'open': quote.get('o'),
                'previous_close': quote.get('pc'),
                'timestamp': pd.Timestamp.fromtimestamp(quote.get('t', 0))
            }
        except Exception as e:
            logger.error(f"Finnhub获取实时报价失败 ({symbol}): {e}")
            raise