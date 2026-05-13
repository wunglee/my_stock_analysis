# -*- coding: utf-8 -*-
"""Backtest session repository.

Provides database access for auto-persisted backtest sessions,
keyed by (stock_code, strategy_id).
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy import select

from src.storage import BacktestSession, DatabaseManager

logger = logging.getLogger(__name__)


class BacktestSessionRepository:
    """DB access layer for auto-persisted backtest sessions."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def upsert(
        self,
        stock_code: str,
        strategy_id: str,
        param_groups: List[dict],
        batch_results: Optional[List[dict]] = None,
    ) -> dict:
        """Create or update a session. If batch_results is None, keeps existing results."""
        with self.db.get_session() as session:
            existing = (
                session.execute(
                    select(BacktestSession).where(
                        BacktestSession.stock_code == stock_code,
                        BacktestSession.strategy_id == strategy_id,
                    )
                )
                .scalars()
                .first()
            )

            if existing:
                existing.param_groups = json.dumps(param_groups, ensure_ascii=False)
                if batch_results is not None:
                    existing.batch_results = json.dumps(batch_results, ensure_ascii=False)
                session.commit()
                return existing.to_dict()

            new_session = BacktestSession(
                stock_code=stock_code,
                strategy_id=strategy_id,
                param_groups=json.dumps(param_groups, ensure_ascii=False),
                batch_results=json.dumps(batch_results, ensure_ascii=False) if batch_results else None,
            )
            session.add(new_session)
            session.commit()
            return new_session.to_dict()

    def get(self, stock_code: str, strategy_id: str) -> Optional[dict]:
        """Get a session by stock and strategy, or None."""
        with self.db.get_session() as session:
            row = (
                session.execute(
                    select(BacktestSession).where(
                        BacktestSession.stock_code == stock_code,
                        BacktestSession.strategy_id == strategy_id,
                    )
                )
                .scalars()
                .first()
            )
            return row.to_dict() if row else None

    def delete(self, stock_code: str, strategy_id: str) -> bool:
        """Delete a session. Returns True if deleted, False if not found."""
        with self.db.get_session() as session:
            row = (
                session.execute(
                    select(BacktestSession).where(
                        BacktestSession.stock_code == stock_code,
                        BacktestSession.strategy_id == strategy_id,
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
