from ..database import SessionLocal
from ..memory_service import memory_service, recall_memories
from ..security import PermissionLevel
from .base import Tool, _STRING_PROP, _schema
from .registry import ToolRegistry


def _memory_save(content: str, category: str = "note") -> dict[str, Any]:
    db = SessionLocal()
    try:
        memory = memory_service.create(db, content=content, category=category)
        return {"memory_id": memory.id, "content": memory.content, "category": memory.category}
    finally:
        db.close()


def _memory_recall(query: str, limit: int = 5) -> dict[str, Any]:
    memories = memory_service.recall(None, query=query, limit=limit)
    return {"query": query, "memories": memories}



def register_memory_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "memory.recall",
            "Recall saved memories relevant to a query, such as the user's preferences and facts.",
            PermissionLevel.LOW,
            _schema({"query": _STRING_PROP}, ["query"]),
            _memory_recall,
        )
    )
    registry.register(
        Tool(
            "memory.save",
            "Save a useful fact or preference to PLUTON's long-term memory.",
            PermissionLevel.LOW,
            _schema({"content": _STRING_PROP, "category": _STRING_PROP}, ["content"]),
            _memory_save,
        )
    )
