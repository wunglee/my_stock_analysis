# -*- coding: utf-8 -*-
"""Backtest parameter template repository.

Provides database access for saved parameter-group templates.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy import desc, select

from src.storage import BacktestParamTemplate, DatabaseManager

logger = logging.getLogger(__name__)


class BacktestTemplateRepository:
    """DB access layer for backtest parameter templates."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def save(self, strategy_id: str, name: str, params: List[dict]) -> dict:
        """Save a new parameter template. Returns the template as a dict."""
        template = BacktestParamTemplate(
            strategy_id=strategy_id,
            name=name,
            params=json.dumps(params, ensure_ascii=False),
        )
        with self.db.get_session() as session:
            session.add(template)
            session.commit()
            return template.to_dict()

    def list_by_strategy(self, strategy_id: str) -> List[dict]:
        """List templates for a strategy, newest first."""
        with self.db.get_session() as session:
            rows = (
                session.execute(
                    select(BacktestParamTemplate)
                    .where(BacktestParamTemplate.strategy_id == strategy_id)
                    .order_by(desc(BacktestParamTemplate.created_at))
                )
                .scalars()
                .all()
            )
            return [r.to_dict() for r in rows]

    def get(self, template_id: int) -> Optional[dict]:
        """Get a single template by ID, or None."""
        with self.db.get_session() as session:
            row = session.get(BacktestParamTemplate, template_id)
            return row.to_dict() if row else None

    def delete(self, template_id: int) -> bool:
        """Delete a template by ID. Returns True if deleted, False if not found."""
        with self.db.get_session() as session:
            row = session.get(BacktestParamTemplate, template_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
