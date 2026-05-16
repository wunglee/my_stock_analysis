# -*- coding: utf-8 -*-
"""
===================================
股票数据服务层
===================================

职责：
1. 封装股票数据获取逻辑
2. 提供实时行情和历史数据接口
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from src.repositories.stock_repo import StockRepository

logger = logging.getLogger(__name__)


class StockService:
    """
    股票数据服务
    
    封装股票数据获取的业务逻辑
    """
    
    def __init__(self):
        """初始化股票数据服务"""
        self.repo = StockRepository()
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时行情
        
        Args:
            stock_code: 股票代码
            
        Returns:
            实时行情数据字典
        """
        try:
            # 调用数据获取器获取实时行情
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            quote = manager.get_realtime_quote(stock_code)
            
            if quote is None:
                logger.warning(f"获取 {stock_code} 实时行情失败")
                return None
            
            # UnifiedRealtimeQuote 是 dataclass，使用 getattr 安全访问字段
            # 字段映射: UnifiedRealtimeQuote -> API 响应
            # - code -> stock_code
            # - name -> stock_name
            # - price -> current_price
            # - change_amount -> change
            # - change_pct -> change_percent
            # - open_price -> open
            # - high -> high
            # - low -> low
            # - pre_close -> prev_close
            # - volume -> volume
            # - amount -> amount
            return {
                "stock_code": getattr(quote, "code", stock_code),
                "stock_name": getattr(quote, "name", None),
                "current_price": getattr(quote, "price", 0.0) or 0.0,
                "change": getattr(quote, "change_amount", None),
                "change_percent": getattr(quote, "change_pct", None),
                "open": getattr(quote, "open_price", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "prev_close": getattr(quote, "pre_close", None),
                "volume": getattr(quote, "volume", None),
                "amount": getattr(quote, "amount", None),
                "update_time": datetime.now().isoformat(),
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，使用占位数据")
            return self._get_placeholder_quote(stock_code)
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}", exc_info=True)
            return None
    
    def get_history_data(
        self,
        stock_code: str,
        period: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取股票历史行情

        Args:
            stock_code: 股票代码
            period: K 线周期 (daily/weekly/monthly)
            days: 获取天数

        Returns:
            历史行情数据字典
        """
        try:
            # 使用新的 history_provider 体系获取数据
            from core.data.history_provider.memory_provider import MemoryCacheProvider
            from core.data.history_provider.db_provider import DbProvider
            from core.data.history_provider.external_provider import ExternalApiProvider
            from core.data.history_provider.multi_source import MultiSourceProvider
            from core.data.history_provider.three_layer import ThreeLayerProvider
            from src.data_provider.bar_repository import SqliteBarRepository
            from src.data_provider.trading_calendar_adapter import XCalTradingCalendar
            from src.storage import DatabaseManager
            from data_provider.base import DataFetcherManager

            calendar = XCalTradingCalendar(market="cn")
            bar_repo = SqliteBarRepository(
                db_manager=DatabaseManager.get_instance(),
                calendar=calendar,
            )

            memory = MemoryCacheProvider()
            db = DbProvider(repository=bar_repo)

            fetcher_mgr = DataFetcherManager()
            fetchers = fetcher_mgr._get_fetchers_snapshot()

            def _make_adapter(fetcher):
                """将 BaseFetcher 适配为 ExternalApiProvider 的接口"""
                def adapter(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
                    df = fetcher.get_daily_data(
                        stock_code=symbol,
                        start_date=start.strftime("%Y-%m-%d"),
                        end_date=end.strftime("%Y-%m-%d"),
                    )
                    return df if df is not None and not df.empty else None
                return adapter

            ext_providers = [
                ExternalApiProvider(name=f.name, fetcher=_make_adapter(f))
                for f in fetchers
            ]
            multi_source = MultiSourceProvider(providers=ext_providers)

            three_layer = ThreeLayerProvider(
                memory=memory,
                db=db,
                multi_source=multi_source,
                calendar=calendar,
            )

            end_date = pd.Timestamp.now()
            start_date = end_date - pd.Timedelta(days=days * 2)

            df = three_layer.fetch(stock_code, start_date, end_date, period)

            if df is None or df.empty:
                logger.warning(f"获取 {stock_code} 历史数据失败")
                return {"stock_code": stock_code, "period": period, "data": []}

            # 获取股票名称
            stock_name = fetcher_mgr.get_stock_name(stock_code)

            # 转换为响应格式
            data = []
            date_col = "trade_date" if "trade_date" in df.columns else "date"
            for _, row in df.iterrows():
                date_val = row.get(date_col)
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)

                data.append({
                    "date": date_str,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)) if row.get("volume") else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") else None,
                    "change_percent": float(row.get("pct_chg", 0)) if row.get("pct_chg") else None,
                })

            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "data": data,
            }

        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"stock_code": stock_code, "period": period, "data": []}
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}", exc_info=True)
            return {"stock_code": stock_code, "period": period, "data": []}
    
    def _get_placeholder_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取占位行情数据（用于测试）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            占位行情数据
        """
        return {
            "stock_code": stock_code,
            "stock_name": f"股票{stock_code}",
            "current_price": 0.0,
            "change": None,
            "change_percent": None,
            "open": None,
            "high": None,
            "low": None,
            "prev_close": None,
            "volume": None,
            "amount": None,
            "update_time": datetime.now().isoformat(),
        }
