"""
多源轮询器 — 仅日线

管理多个 ExternalApiProvider，按优先级轮询，
首次命中即返回。

不实现 IDataProvider，使用独立接口 fetch_daily()。
调用方（ThreeLayerProvider）告诉它取什么日期范围的日线，它就去取。
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd

from .external_provider import ExternalApiProvider

logger = logging.getLogger(__name__)


class MultiSourceProvider:
    """多源日线轮询器

    职责：按优先级顺序轮询多个 ExternalApiProvider，
    首个返回有效数据的 provider 的结果被采用。

    无 period 参数。无缺失判断能力。纯执行者。
    """

    def __init__(self, providers: List[ExternalApiProvider] | None = None) -> None:
        self._providers: List[ExternalApiProvider] = list(providers) if providers else []

    def add_provider(self, provider: ExternalApiProvider) -> None:
        """添加数据源（追加到列表末尾）"""
        self._providers.append(provider)

    @property
    def providers(self) -> List[ExternalApiProvider]:
        """返回当前管理的 provider 列表"""
        return list(self._providers)

    def fetch_daily(
        self,
        symbol: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame | None:
        """按优先级轮询获取日线数据

        Args:
            symbol: 证券代码
            start_date: 开始日期（包含）
            end_date: 结束日期（包含）

        Returns:
            DataFrame columns: trade_date, open, high, low, close, volume[, ...]
            所有源都失败时返回 None
        """
        total = len(self._providers)
        errors: List[str] = []

        for attempt, provider in enumerate(self._providers, start=1):
            logger.info(
                f"[MultiSource] 尝试 {attempt}/{total}: {provider.name} 获取 {symbol}"
            )
            df = provider.fetch(symbol, start_date, end_date)
            if df is not None and not df.empty:
                logger.info(
                    f"[MultiSource] {symbol} 使用 {provider.name} 获取成功, rows={len(df)}"
                )
                return df
            errors.append(provider.name)

        logger.warning(
            f"[MultiSource] {symbol} 所有 {total} 个数据源均失败: {', '.join(errors)}"
        )
        return None
