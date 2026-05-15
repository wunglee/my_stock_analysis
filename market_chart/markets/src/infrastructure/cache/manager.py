"""
三层缓存管理器 - 统一管理 Memory → DB → 外部数据源

核心策略：
1. 按时间窗口粒度缓存（月/周，最小粒度为周）
2. 三层缓存顺序：Memory → DB → 外部API
3. 逐窗口查询，精细化缓存利用
4. 回写机制：所有新数据自动写入各层缓存

职责：
- 管理三层缓存的协调工作
- 提供统一的数据获取接口
- 处理缺失窗口的逐层查询
"""

import logging
from typing import Callable, Optional

import pandas as pd

from core.share.market.market_enums import MarketCode
from core.share.market.market_utils import MarketUtils
from core.share.market.trading_calendar_service import get_trading_calendar_service
from .db import DBCache
from .window_cache import WindowsCache

logger = logging.getLogger('ThreeLayerCacheManager')


class ThreeLayerCacheManager:
    """
    三层窗口化缓存管理器

    缓存层级：
    1. Memory (永不过期)
    2. Database (持久化)
    3. External API (最后调用)

    窗口粒度：最小为周（weekly），避免过度碎片化
    """

    def __init__(
            self,
            db_service=None,
    ):
        """
        初始化三层缓存管理器

        Args:
            db_service: 数据库服务实例
        
        Note:
            ✨ 所有参数默认为None，优先从 markets/config/{env}/cache.yml 读取
            仅当显式传入非eNone值时，才使用传入的参数（用于测试场景）
        """

        # 窗口管理器
        self._window_cache = WindowsCache()

        # 数据库缓存
        self._db_cache = DBCache(db_service=db_service)

        # 交易日历服务（用于判断连续性）
        self._calendar_service = get_trading_calendar_service()

    def get_data(
            self,
            symbol: str,
            from_date: pd.Timestamp,
            to_date: pd.Timestamp,
            period: str = 'daily',
            market_code: Optional[MarketCode] = None,
            db_fetch_func: Callable[..., pd.DataFrame] = None,
            api_fetch_func: Callable[..., pd.DataFrame] = None,
            db_save_func: Callable[..., None] = None,
            current_time: pd.Timestamp = None
    ) -> pd.DataFrame:
        """
        获取数据（三层缓存核心方法）
        
        流程：
        1. 生成所需的所有窗口键（使用 self._window_size）
        2. 从快速缓存获取已有窗口
        3. 检测当前周：
           - 如果是当前周，强制重新查询（每天更新）
           - 即使查询结束日期 < 本周末（如上市日），也必须刷新
           - 原因：今天之后的查询可能包含更多天，避免缓存过时
        4. 对缺失窗口逐个进行三层查询：
           - 先查 DB（使用 db_fetch_func）
           - DB 未命中调用外部 API（使用 api_fetch_func）
        5. 所有新数据写入各层缓存
        6. 合并所有窗口并返回
        
        Args:
            symbol: 股票/指数代码
            from_date: 开始日期（YYYY-MM-DD）
            to_date: 结束日期（YYYY-MM-DD）
            period: 数据粒度/K线类型 (daily/weekly/monthly，默认 daily)
                    注意：period 必须 ≤ window_size
            market_code: 市场代码枚举 (MarketCode.CN/US/HK/JP/EU/SG)，用于交易日历判断，如为None则从 symbol 推断
            db_fetch_func: 数据库查询函数，签名为 func(start_date, end_date, period) -> DataFrame
            api_fetch_func: API查询函数，签名为 func(start_date, end_date, period) -> DataFrame
            db_save_func: 数据库回存函数，签名为 func(df) -> None。在 API 拉取成功后调用，用于将数据持久化到 DB 层
            current_time:当前时间
        Returns:
            完整的 DataFrame
        """
        # 推断市场代码（用于交易日历）
        if market_code is None:
            market_code = MarketUtils.infer_market_from_symbol(symbol)

        cached_windows, missing_windows = self._window_cache.get_cached_and_missing_windows(symbol,
                                                                                            from_date,
                                                                                            to_date,
                                                                                            market_code,
                                                                                            period,
                                                                                            current_time)
        # ========== 第3步：处理缺失窗口（合并连续窗口，批量查询）==========
        if missing_windows:
            logger.info(f"🔍 缺失 {len(missing_windows)} 个窗口，开始三层查询")

            # 🔧 关键优化：合并连续未命中窗口，减少网络请求次数
            merged_ranges = self._window_cache.merge_continuous_windows(missing_windows, period)
            logger.info(f"🔧 合并后: {len(merged_ranges)} 个连续范围 (原 {len(missing_windows)} 个窗口)")

            # ⚠️ 工作区：for 循环自然结束时会触发 pandas/numpy 段错误，必须使用 break 显式退出
            merged_ranges_list = list(merged_ranges)

            for loop_index in range(len(merged_ranges_list)):
                range_info = merged_ranges_list[loop_index]
                range_start = range_info['start']
                range_end = range_info['end']
                range_windows = range_info['windows']  # 该范围包含的窗口键列表

                logger.info(
                    f"📊 批量查询: {range_start.strftime('%Y-%m-%d')} ~ {range_end.strftime('%Y-%m-%d')} (包含 {len(range_windows)} 个窗口)")

                # 3.1 尝试从数据库获取大范围数据
                db_df = None
                if db_fetch_func:
                    db_df = db_fetch_func(range_start, range_end, period=period)

                # 分配数据到各个窗口
                if db_df is not None and not db_df.empty:
                    logger.info(f"✅ 数据库批量命中: {range_start.strftime('%Y-%m-%d')} ~ {range_end.strftime('%Y-%m-%d')} ({len(db_df)} 条)")
                    # 分配数据到各个窗口
                    self._window_cache.distribute_data_to_windows(symbol, period, db_df, range_windows, cached_windows,
                                                                  from_date, market_code)
                    continue
                # 3.2 数据库也未命中，调用外部 API
                logger.info(f"🌐 API批量查询: {range_start} ~ {range_end}")
                try:
                    api_df = None
                    if api_fetch_func:
                        api_df = api_fetch_func(range_start, range_end, period=period)
                except Exception as e:
                    logger.error(
                        f"❌ API批量查询失败: {range_start.strftime('%Y-%m-%d')} ~ {range_end.strftime('%Y-%m-%d')}, error={e}")
                    raise
                try:
                    if api_df is not None and not api_df.empty:
                        logger.info(
                            f"✅ API批量返回: {range_start.strftime('%Y-%m-%d')} ~ {range_end.strftime('%Y-%m-%d')} ({len(api_df)} 条)")

                        self._window_cache.distribute_data_to_windows(symbol, period, api_df, range_windows,
                                                                      cached_windows, from_date, market_code)
                        if db_save_func:
                            db_save_func(api_df)
                    else:
                        logger.warning(
                            f"⚠️ API无数据: {range_start.strftime('%Y-%m-%d')} ~ {range_end.strftime('%Y-%m-%d')}，标记 {len(range_windows)} 个空窗口")
                        for _wk in range_windows:
                            self._window_cache._fast_cache.set(symbol, period, _wk, known_empty=True)
                except Exception as e:
                    logger.error(
                        f"❌ 缓存窗口分配失败: {range_start.strftime('%Y-%m-%d')} ~ {range_end.strftime('%Y-%m-%d')}, error={e}, type={type(e).__name__}",
                        exc_info=True)
                    raise

                # ⚠️ 工作区：必须使用 break 显式退出循环，避免 for 循环自然结束时触发 pandas/numpy 段错误
                api_df = None
                if loop_index >= len(merged_ranges_list) - 1:
                    break

        # ========== 第4步：合并所有窗口数据并返回 ==========

        if not cached_windows:
            logger.warning(
                f"⚠️ 所有窗口都无数据: {symbol} {from_date.strftime('%Y-%m-%d')}~{to_date.strftime('%Y-%m-%d')}")
            return pd.DataFrame()

        try:
            # 按窗口键排序并合并
            sorted_keys = sorted(cached_windows.keys())
            result_dfs = [cached_windows[key] for key in sorted_keys]
            result_df = pd.concat(result_dfs, ignore_index=True)
        except Exception as e:
            logger.error(f"❌ 合并窗口数据失败: {e}", exc_info=True)
            raise

        try:
            # 精确筛选日期范围
            if 'date' in result_df.columns:
                result_df['date'] = pd.to_datetime(result_df['date'])
                start_dt = pd.to_datetime(from_date)
                end_dt = pd.to_datetime(to_date)
                result_df = result_df[(result_df['date'].values >= start_dt.to_datetime64()) & (result_df['date'].values
                                                                                            <= end_dt.to_datetime64())]
        except Exception as e:
            logger.error(f"❌ 日期筛选失败: {e}", exc_info=True)
            raise

        logger.info(f"✅ 返回数据: {len(result_df)} 条 (来自 {len(cached_windows)} 个窗口)")
        return result_df
