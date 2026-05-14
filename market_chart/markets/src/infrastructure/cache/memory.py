"""
内存缓存层 - 窗口级别的 LRU + TTL 缓存

职责：
1. 按窗口粒度缓存数据（symbol:period:window_key）
2. LRU 淘汰策略（OrderedDict）
3. TTL 过期机制
4. 窗口级别的读写

注意：
- 缓存键必须包含 period（数据粒度/K线类型）
- period 是数据的本质属性（daily/weekly/monthly）
- period 必须 ≤ window_size
"""

import logging
import time
from typing import Optional, Dict
from collections import OrderedDict
import pandas as pd

logger = logging.getLogger('MemoryCache')


class MemoryCache:
    """内存缓存层（LRU + TTL）"""
    
    def __init__(self, max_windows: int = 1000, ttl: int | None = None):
        """
        初始化内存缓存

        Args:
            max_windows: 最大缓存窗口数（默认1000）
            ttl: 缓存过期时间（秒，None=永不过期）
        """
        self._cache: OrderedDict[str, Dict] = OrderedDict()
        self._max_windows = max_windows
        self._ttl = ttl
        ttl_label = "永不过期" if ttl is None else f"{ttl}s"
        logger.info(f"✅ MemoryCache 初始化: max_windows={max_windows}, ttl={ttl_label}")
    
    def get(self, symbol: str, period: str, window_key: str) -> Optional[Dict]:
        """
        获取单个窗口数据（包含元数据）
        
        Args:
            symbol: 股票/指数代码
            period: 数据粒度（daily/weekly/monthly，K线类型）
            window_key: 窗口键
        
        Returns:
            Dict {
                'data': DataFrame,           # 实际数据
                'is_first_window': bool,     # 是否为起始窗口（最早数据）
                'timestamp': float           # 缓存时间戳
            } 或 None
        """
        cache_key = f"{symbol}:{period}:{window_key}"
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            
            # 检查过期（ttl=None 时永不过期）
            if self._ttl is None or time.time() - cached['timestamp'] < self._ttl:
                self._cache.move_to_end(cache_key)
                logger.debug(f"✅ 内存命中: {cache_key}")
                return cached
            else:
                del self._cache[cache_key]
                logger.debug(f"🗑️ 缓存过期: {cache_key}")
        
        return None
    
    def set(self, symbol: str, period: str, window_key: str,
            data: Optional[pd.DataFrame] = None,
            is_first_window: bool = False,
            known_empty: bool = False) -> None:
        """
        写入单个窗口数据（包含元数据）

        两种写入模式:
        - 正常数据: set(..., data=df)
        - 已知空窗口: set(..., known_empty=True)  — 不需传 data，只记标记

        Args:
            symbol: 股票/指数代码
            period: 数据粒度（daily/weekly/monthly，K线类型）
            window_key: 窗口键
            data: 数据（known_empty=True 时可为 None）
            is_first_window: 是否为起始窗口（最早数据）
            known_empty: 调用方显式声明「已确认该窗口无数据」
        """
        if (data is None or data.empty) and not known_empty:
            return

        cache_key = f"{symbol}:{period}:{window_key}"

        # LRU淘汰
        if len(self._cache) >= self._max_windows:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"🗑️ LRU淘汰: {oldest_key}")

        self._cache[cache_key] = {
            'data': data.copy() if data is not None else None,
            'is_first_window': is_first_window,
            'timestamp': time.time(),
            'known_empty': known_empty,
        }

        empty_flag = "🏷️已知空 " if known_empty else ""
        first_flag = "🅰️ " if is_first_window else ""
        row_count = len(data) if data is not None else 0
        logger.debug(f"✅ 内存写入: {empty_flag}{first_flag}{cache_key} ({row_count} 条)")
    
    def update_first_window_flag(self, symbol: str, period: str, window_key: str, is_first_window: bool) -> bool:
        """
        更新指定窗口的 is_first_window 标记（用于回溯更新）
        
        Args:
            symbol: 股票/指数代码
            period: 数据粒度（daily/weekly/monthly，K线类型）
            window_key: 窗口键
            is_first_window: 新的标记值
        
        Returns:
            bool: 是否成功更新（如果窗口不存在则返回False）
        """
        cache_key = f"{symbol}:{period}:{window_key}"
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            
            # 检查过期（ttl=None 时永不过期）
            if self._ttl is None or time.time() - cached['timestamp'] < self._ttl:
                # 更新标记
                old_flag = cached['is_first_window']
                cached['is_first_window'] = is_first_window
                
                if old_flag != is_first_window:
                    logger.info(f"🔄 回溯更新窗口标记: {cache_key} (is_first_window: {old_flag} → {is_first_window})")
                
                return True
            else:
                # 过期删除
                del self._cache[cache_key]
                logger.debug(f"🗑️ 缓存过期: {cache_key}")
        
        return False
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("✅ 内存缓存已清空")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_windows': len(self._cache),
            'max_windows': self._max_windows,
            'usage_percent': len(self._cache) / self._max_windows * 100
        }
