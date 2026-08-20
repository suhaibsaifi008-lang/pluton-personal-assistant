"""Centralized service for long-term memory persistence, FTS5 sync, and recall."""
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .models import Memory


class MemoryService:
    """Manages memory creation, deletion, FTS5 indexing, and BM25 relevance recall."""

    def create(self, db: Session, content: str, category: str = "note") -> Memory:
        """Create a new memory record and synchronize it to the FTS5 index."""
        memory = Memory(content=content, category=category or "note")
        db.add(memory)
        db.commit()
        db.refresh(memory)
        try:
            db.connection().exec_driver_sql(
                "INSERT INTO memories_fts (id, content, category) VALUES (?, ?, ?)",
                (memory.id, memory.content, memory.category),
            )
            db.commit()
        except Exception:
            pass
        return memory

    def delete(self, db: Session, memory_id: str) -> bool:
        """Delete a memory record and its corresponding FTS5 entry. Returns False if not found."""
        memory = db.get(Memory, memory_id)
        if not memory:
            return False
        db.delete(memory)
        try:
            db.connection().exec_driver_sql("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
        except Exception:
            pass
        db.commit()
        return True

    def list_all(self, db: Session) -> list[Memory]:
        """List all memories ordered by creation time descending."""
        return list(db.scalars(select(Memory).order_by(Memory.created_at.desc())))

    def recall(self, db: Session | None, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Return memories relevant to `query`, ranked by relevance (FTS5 BM25 with token-overlap fallback)."""
        settings = get_settings()
        limit = limit or settings.memory_context_limit
        owns_session = db is None
        session = db or SessionLocal()
        try:
            raw_tokens = re.findall(r"[\w]+", query.lower())
            tokens = [t for t in raw_tokens if len(t) > 1]

            # 1. Try SQLite FTS5 search with BM25 ranking if query tokens exist
            if tokens:
                fts_query = " OR ".join(f'"{t}"*' for t in tokens)
                try:
                    rows = session.connection().exec_driver_sql(
                        """
                        SELECT id, content, category, rank
                        FROM memories_fts
                        WHERE memories_fts MATCH ?
                        ORDER BY rank ASC
                        LIMIT ?
                        """,
                        (fts_query, limit),
                    ).fetchall()
                    if rows:
                        return [{"id": r[0], "content": r[1], "category": r[2]} for r in rows]
                except Exception:
                    pass

            # 2. Fallback to scoring against memories table
            all_memories = session.scalars(select(Memory).order_by(Memory.created_at.desc())).all()
            if not tokens:
                return [{"id": m.id, "content": m.content, "category": m.category} for m in all_memories[:limit]]

            scored = []
            token_set = set(tokens)
            for mem in all_memories:
                mem_tokens = set(re.findall(r"[\w]+", f"{mem.content} {mem.category}".lower()))
                overlap = len(token_set & mem_tokens)
                if overlap > 0:
                    scored.append((overlap, mem))

            scored.sort(key=lambda item: item[0], reverse=True)
            selected = [item[1] for item in scored] or list(all_memories[:limit])
            return [{"id": m.id, "content": m.content, "category": m.category} for m in selected[:limit]]
        finally:
            if owns_session:
                session.close()


memory_service = MemoryService()


def recall_memories(query: str, limit: int | None = None, db: Session | None = None) -> list[dict[str, Any]]:
    """Convenience helper delegating to memory_service.recall."""
    return memory_service.recall(db, query, limit)
