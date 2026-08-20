"""PLUTON V2 Memory Store Interface & Implementation.

Formal boundary for:
- Semantic Memory (world facts, user preferences)
- Episodic Memory (past task executions and outcomes)
- Procedural Memory (learned multi-step macros / workflow strategies)
- Project Memory (codebase-specific context, files, paths).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.contracts import MemoryCategory, MemoryRecord
from ..models import Memory

logger = logging.getLogger("pluton.memory")


class MemoryStore:
    """Canonical repository interface for long-term agent memory."""

    def create_record(
        self,
        db: Session,
        content: str,
        category: MemoryCategory = MemoryCategory.SEMANTIC,
        source: str = "user",
        confidence: float = 1.0,
        provenance: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Persist a new memory record."""
        clean_content = content.strip()
        record = MemoryRecord(
            content=clean_content,
            category=category,
            source=source,
            confidence=confidence,
            provenance=provenance,
            metadata=metadata or {},
        )
        db_model = Memory(
            id=record.id,
            content=record.content,
            category=record.category.value,
            created_at=record.timestamp,
        )
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return record

    def list_records(
        self,
        db: Session,
        category: MemoryCategory | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """List persisted memory records."""
        query = select(Memory)
        if category:
            query = query.where(Memory.category == category.value)
        query = query.order_by(Memory.created_at.desc()).limit(limit)

        records: list[MemoryRecord] = []
        for row in db.scalars(query).all():
            cat_enum = MemoryCategory.SEMANTIC
            try:
                cat_enum = MemoryCategory(row.category)
            except Exception:
                pass
            records.append(MemoryRecord(
                id=row.id,
                content=row.content,
                category=cat_enum,
                timestamp=row.created_at,
            ))
        return records

    def recall_relevant(
        self,
        db: Session,
        query_text: str,
        limit: int = 5,
        category: MemoryCategory | None = None,
    ) -> list[MemoryRecord]:
        """Recall records scored by relevance tokens."""
        all_records = self.list_records(db, category=category, limit=200)
        if not all_records or not query_text.strip():
            return []

        query_tokens = set(query_text.lower().split())
        scored: list[tuple[float, MemoryRecord]] = []
        for r in all_records:
            record_tokens = set(r.content.lower().split())
            overlap = len(query_tokens & record_tokens)
            if overlap > 0:
                scored.append((float(overlap), r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def delete_record(self, db: Session, record_id: str) -> bool:
        """Remove a memory record by ID."""
        row = db.get(Memory, record_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True


MEMORY_STORE = MemoryStore()
