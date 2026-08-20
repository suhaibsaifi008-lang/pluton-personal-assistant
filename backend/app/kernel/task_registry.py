"""
PLUTON V2 — Active Task Registry
Authoritative registry of currently executing tasks in Pluton.
Guarantees full visibility, worker tracking, cancellation propagation, and zero active tasks when idle.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("pluton.kernel.task_registry")


@dataclass
class ActiveTaskEntry:
    task_id: str
    session_id: str | None
    state: str
    created_at: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    current_action: str | None = None
    current_worker: str | None = None
    token_status: str = "VALID"
    is_cancelled: bool = False
    asyncio_tasks: list[asyncio.Task[Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "state": self.state,
            "created_at": datetime.fromtimestamp(self.created_at, tz=timezone.utc).isoformat(),
            "started_at": datetime.fromtimestamp(self.started_at, tz=timezone.utc).isoformat(),
            "last_activity_at": datetime.fromtimestamp(self.last_activity_at, tz=timezone.utc).isoformat(),
            "current_action": self.current_action,
            "current_worker": self.current_worker,
            "token_status": self.token_status,
            "is_cancelled": self.is_cancelled,
            "active_worker_count": len([t for t in self.asyncio_tasks if not t.done()]),
        }


class ActiveTaskRegistry:
    """Thread-safe runtime registry of all in-flight tasks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, ActiveTaskEntry] = {}
        self._cancelled_tasks: set[str] = set()

    def is_cancelled(self, task_id: str) -> bool:
        """Return True if the task has been marked cancelled."""
        with self._lock:
            if task_id in self._cancelled_tasks:
                return True
            entry = self._tasks.get(task_id)
            return bool(entry and entry.is_cancelled)

    def register_task(
        self,
        task_id: str,
        session_id: str | None = None,
        state: str = "RUNNING",
    ) -> ActiveTaskEntry:
        """Register a new active task in the runtime."""
        with self._lock:
            entry = ActiveTaskEntry(
                task_id=task_id,
                session_id=session_id,
                state=state,
            )
            self._tasks[task_id] = entry
            logger.info("[TASK_REGISTRY] Registered active task: %s (Total active: %d)", task_id, len(self._tasks))
            return entry

    def unregister_task(self, task_id: str, reason: str = "completed") -> None:
        """Unregister and purge a completed or terminated task."""
        with self._lock:
            entry = self._tasks.pop(task_id, None)
            if entry:
                # Cancel any dangling asyncio tasks registered for this task
                for t in entry.asyncio_tasks:
                    if not t.done():
                        t.cancel()
                logger.info("[TASK_REGISTRY] Unregistered task: %s (Reason: %s, Remaining active: %d)", task_id, reason, len(self._tasks))

    def update_task_state(
        self,
        task_id: str,
        state: str | None = None,
        current_action: str | None = None,
        token_status: str | None = None,
    ) -> None:
        """Update runtime state and activity timestamp for an active task."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry.last_activity_at = time.time()
                if state:
                    entry.state = state
                if current_action is not None:
                    entry.current_action = current_action
                if token_status is not None:
                    entry.token_status = token_status

    def mark_cancelled(self, task_id: str, reason: str = "user_cancelled") -> None:
        """Mark a task as cancelled and cancel all bound workers immediately."""
        with self._lock:
            self._cancelled_tasks.add(task_id)
            entry = self._tasks.get(task_id)
            if entry:
                entry.is_cancelled = True
                entry.token_status = "REVOKED"
                entry.state = "CANCELLED"
                for t in entry.asyncio_tasks:
                    if not t.done():
                        t.cancel()
                logger.warning("[TASK_REGISTRY] Task marked CANCELLED: %s (%s)", task_id, reason)

    cancel_task = mark_cancelled

    def attach_worker(self, task_id: str, task: asyncio.Task[Any]) -> None:
        """Attach an asyncio Task to the task lifecycle."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry.asyncio_tasks.append(task)

    def get_task(self, task_id: str) -> ActiveTaskEntry | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_active_tasks(self) -> list[dict[str, Any]]:
        """Return diagnostic JSON serialization of all active tasks."""
        with self._lock:
            return [entry.to_dict() for entry in self._tasks.values()]

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    def purge_all(self, reason: str = "emergency_shutdown") -> list[str]:
        """Cancel and purge every active task in the registry."""
        with self._lock:
            task_ids = list(self._tasks.keys())
            for tid in task_ids:
                self.mark_cancelled(tid, reason=reason)
                self.unregister_task(tid, reason=reason)
            return task_ids


ACTIVE_TASK_REGISTRY = ActiveTaskRegistry()
