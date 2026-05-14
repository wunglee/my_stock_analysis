"""
Tushare数据提供者 - A股/港股数据源
实现HistoricalDataProvider接口

职责：
- 通过Tushare Pro API获取A股和港股历史数据
- 支持指数和个股数据获取
- 数据标准化和质量验证
- 实现统一的HistoricalDataProvider接口

依赖：
pip install tushare
需要token: https://tushare.pro/register

优势：
- A股数据质量高
- 港股数据较为完整
- 需要注册获取token

配置：
- 需要Token（从 https://tushare.pro/register 注册获取）
- 环境变量：TUSHARE_TOKEN
- 或通过credentials.yml配置
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, Any

import pandas as pd

from core.data.providers.base_provider import BaseDataProvider
# 导入新的数据结构
from core.data.providers.protocols import PriceData
from core.share.config_manager import ConfigManager
from core.share.market.data_types import OHLCVRecord

logger = logging.getLogger('Tushare')


@dataclass
class TushareConfig:
    """Tushare配置数据类"""
    test_symbol: str = "000001.SZ"  # 默认测试符号（平安银行）
    timeout: int = 30  # 请求超时（秒）
    max_retries: int = 3  # 最大重试次数


class TushareDataProvider(BaseDataProvider):
    """Tushare数据提供者"""
    
    def __init__(self):
        """
        初始化Tushare数据提供者
        
        Note:
            - token 从配置文件读取（credentials.yml）
            - proxy 从配置文件读取，不通过参数传递
            - 💚 不再使用 os.environ，统一使用 ConfigManager
        """
        # 💚 调用基类构造函数（初始化缓存）
        super().__init__()
        
        # 💚 从配置文件读取 Token（不再使用环境变量）
        token = self._load_token_from_config()
        self.ts_pro = None
        
        # 从配置文件中获取proxy
        config_manager = ConfigManager()
        proxy_config = config_manager.get_proxies_from_config()
        if proxy_config:
            # 使用HTTP代理（如果有配置的话）
            self.proxy = proxy_config.get('http') or proxy_config.get('socks5')
        else:
            self.proxy = None
        
        # 尝试初始化Tushare
        try:
            import tushare as ts
            
            if token:
                ts.set_token(token)
                self.ts_pro = ts.pro_api()
                logger.info(f"Tushare API initialized successfully with token: {token[:8]}...")
            else:
                self.ts_pro = None
                logger.warning("Tushare token not provided. API will not be available.")
                self.available = False
                return
                
        except ImportError:
            logger.error("tushare not installed. Please run: pip install tushare")
            self.available = False
            return
        except Exception as e:
            logger.error(f"Failed to initialize Tushare: {e}")
            self.available = False
            return
        
        # 测试连接
        try:
            # 简单测试连接
            self.ts_pro.trade_cal(exchange='SSE', start_date='20230101', end_date='20230101')
            self.available = True
            logger.info("Tushare API connection test successful")
        except Exception as e:
            logger.error(f"Tushare API connection test failed: {e}")
            self.available = False
    
    def _load_token_from_config(self) -> Optional[str]:
        """
        从配置文件加载Tushare Token
        
        Returns:
            Tushare Token字符串，如果未找到则返回None
        """
        try:
            config_manager = ConfigManager()
            # 获取凭证配置路径
            credentials_path = config_manager.get_config_path('credentials')
            
            # 检查凭证文件是否存在
            if os.path.exists(credentials_path):
                import yaml
                with open(credentials_path, 'r', encoding='utf-8') as f:
                    credentials = yaml.safe_load(f)
                    if credentials and 'tushare' in credentials:
                        return credentials['tushare'].get('token')
        except Exception as e:
            logger.warning(f"Failed to load Tushare token from config: {e}")
        
        return None
    
    def get_test_symbol(self) -> str:
        """获取测试符号"""
        return "000001.SZ"  # 平安银行
    
    def initialize(self, credential:str, **kwargs):
        """
        初始化方法，用于运行时初始化客户端
        
        Args:
            credential: 包含API密钥的凭证字典
        """
        if credential:
            try:
                import tushare as ts
                ts.set_token(credential)
                self.ts_pro = ts.pro_api()
                self.available = True
                logger.info("Tushare client initialized successfully with provided token")
            except Exception as e:
                logger.error(f"Failed to initialize Tushare client: {e}")
                self.available = False
        else:
            logger.warning("No token provided for Tushare initialization")
            self.available = False
    
    def get_index_prices(
        self,
        symbol: str,
        start_date:pd.Timestamp,
        end_date: pd.Timestamp,
        current_time: pd.Timestamp,
        period: str = 'daily'
    ) -> PriceData:
        """
        获取指数历史价格数据
        
        Args:
            symbol: 指数ID（如 "000001.SH"）
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            PriceData: 标准化的价格数据
            
        Raises:
            ValueError: 当无法获取有效数据时
        """
        if not self.available or self.ts_pro is None:
            raise RuntimeError("Tushare API not available")
            
        # 转换日期格式
        start_date_str = start_date.strftime('%Y%m%d')
        end_date_str = end_date.strftime('%Y%m%d')
        
        logger.info(f"Fetching index data for {symbol} from {start_date_str} to {end_date_str}")
        
        try:
            # 调用Tushare API获取指数行情数据
            df = self.ts_pro.index_daily(ts_code=symbol, start_date=start_date_str, end_date=end_date_str)
            
            if df is None or df.empty:
                raise ValueError(f"No data returned for {symbol}")
            
            # 标准化数据格式
            standardized_data = self._standardize_format(df, symbol)
            self.set_needs_realtime_kline(standardized_data, current_time)
            logger.info(f"Successfully fetched {len(standardized_data.records)} records for {symbol}")
            return standardized_data
            
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            raise ValueError(f"Failed to fetch data for {symbol}: {str(e)}")
    
    def get_stock_prices(
        self,
        stock_id: str,
        start_date:pd.Timestamp,
        end_date: pd.Timestamp,
        market_local_time: pd.Timestamp,
        period: str = 'daily'
    ) -> PriceData:
        """
        获取个股历史价格数据
        
        💚 注意: 此方法由基类处理缓存，不需覆写
        
        Args:
            stock_id: 股票ID（如 "000001.SZ"）
            start_date: 开始日期
            end_date: 结束日期
            market_local_time: 目标市场当前本地时间（不带时区信息）
            period: 周期
            
        Returns:
            PriceData: 标准化的价格数据
            
        Raises:
            ValueError: 当无法获取有效数据时
        """
        # 💚 由基类自动处理缓存
        return super().get_stock_prices(stock_id, start_date, end_date, market_local_time, period)
    
    def _fetch_history_kline_from_external_api(self, symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp, period: str = 'daily') -> PriceData:
        """
        从 Tushare API 获取数据（实现基类抽象方法）
        
        💚 注意:
        - 此方法仅供内部使用
        - 外部调用者应使用 get_index_prices() 或 get_stock_prices()
        - 基类已自动处理缓存
        
        Args:
            symbol: 股票/指数代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: 周期 ('daily', 'weekly', 'monthly')
        
        Returns:
            PriceData: 价格数据对象
        """
        # 判断是指数还是股票
        # 指数代码：000XXX.SH (上证指数)、399XXX.SZ (深证指数)
        # 股票代码：000XXX.SZ (深市主板)、6XXXXX.SH (上市)等
        is_index = False
        if symbol.endswith('.SH') and symbol.startswith('000'):
            # 上证指数
            is_index = True
        elif symbol.endswith('.SZ') and symbol.startswith('399'):
            # 深证指数
            is_index = True
        
        if is_index:
            # 调用原有的 get_index_prices 逻辑
            from core.share.market.market_time_utils import MarketTimeUtils
            market_local_time = MarketTimeUtils.get_market_time_now(symbol)
            price_data = self.get_index_prices(symbol, start_date, end_date, market_local_time)
        else:
            # 调用原有的 get_stock_prices 逻辑
            # 为了避免循环调用，直接实现逻辑
            if not self.available or self.ts_pro is None:
                raise RuntimeError("Tushare API not available")
                
            # 转换日期格式
            start_date_str = start_date.strftime('%Y%m%d')
            end_date_str = end_date.strftime('%Y%m%d')
            
            logger.info(f"Fetching stock data for {symbol} from {start_date_str} to {end_date_str}")
            
            try:
                # 调用Tushare API获取股票行情数据
                df = self.ts_pro.daily(ts_code=symbol, start_date=start_date_str, end_date=end_date_str)
                
                if df is None or df.empty:
                    raise ValueError(f"No data returned for {symbol}")
                
                # 标准化数据格式
                price_data = self._standardize_format(df, symbol)
                
                logger.info(f"Successfully fetched {len(price_data.records)} records for {symbol}")
                
            except Exception as e:
                logger.error(f"Failed to fetch data for {symbol}: {e}")
                raise ValueError(f"Failed to fetch data for {symbol}: {str(e)}")
        
        return price_data
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情数据
        
        Args:
            symbol: 证券代码
            
        Returns:
            Dict: 实时行情数据
        """
        if not self.available or self.ts_pro is None:
            raise RuntimeError("Tushare API not available")
            
        try:
            # 获取实时行情
            df = self.ts_pro.quote(ts_code=symbol)
            
            if df is None or df.empty:
                return {}
            
            # 返回第一条记录的字典形式
            return df.iloc[0].to_dict()
            
        except Exception as e:
            logger.error(f"Failed to fetch quote for {symbol}: {e}")
            return {}
    
    def _standardize_format(self, data: pd.DataFrame, symbol: str) -> PriceData:
        """
        标准化Tushare返回的数据格式
        
        Args:
            data: Tushare返回的原始数据
            symbol: 证券代码
            
        Returns:
            PriceData: 标准化后的数据
        """
        if data is None or data.empty:
            return PriceData(
                symbol=symbol, 
                records=[], 
                start_date=pd.Timestamp.now(),
                end_date=pd.Timestamp.now(),
                count=0
            )
        
        records = []
        for _, row in data.iterrows():
            try:
                # Tushare的日期字段名为trade_date
                date = pd.to_datetime(row['trade_date'], format='%Y%m%d')
                
                record = OHLCVRecord(
                    date=date,  # 使用date而非timestamp
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=int(row['vol'])  # Tushare使用vol字段表示成交量
                )
                records.append(record)
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Skipping invalid row for {symbol}: {e}")
                continue
        
        # 按时间戳排序
        records.sort(key=lambda x: x.date)
        
        # 计算start_date和end_date
        start_date = records[0].date if records else pd.Timestamp.now()
        end_date = records[-1].date if records else pd.Timestamp.now()
        
        return PriceData(
            symbol=symbol, 
            records=records,
            start_date=start_date,
            end_date=end_date,
            count=len(records)
        )
    
    # validate_data_quality方法已迁移到data_quality_utils.py
    # 请使用: from core.data.quality.data_quality_utils import validate_data_quality