"""PLUTON V2 Unified Task Execution Event Bus & Observability.

Provides structured observability across the full task lifecycle:
- TASK_CREATED
- PLAN_CREATED
- STEP_STARTED
- ACTION_STARTED
- ACTION_COMPLETED
- VERIFICATION_STARTED
- VERIFICATION_COMPLETED
- APPROVAL_REQUIRED
- APPROVAL_RESOLVED
- RETRY / REPLAN
- TASK_COMPLETED / FAILED / CANCELLED / TIMED_OUT
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Callable

from ..core.contracts import EventType, TaskEvent

logger = logging.getLogger("pluton.events")


class TaskEventBus:
    """Pub/sub event streaming engine for task execution observability."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[TaskEvent]]] = {}
        self._global_listeners: list[Callable[[TaskEvent], Any]] = []

    def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]:
        """Subscribe to live events for a specific task."""
        q: asyncio.Queue[TaskEvent] = asyncio.Queue()
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(q)
        return q

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[TaskEvent]) -> None:
        """Remove a task subscriber queue."""
        if task_id in self._subscribers:
            try:
                self._subscribers[task_id].remove(queue)
                if not self._subscribers[task_id]:
                    del self._subscribers[task_id]
            except ValueError:
                pass

    def emit(self, event_type: EventType, task_id: str, data: dict[str, Any] | None = None) -> TaskEvent:
        """Publish a structured event to all interested subscribers."""
        ev = TaskEvent(
            event_type=event_type,
            task_id=task_id,
            data=data or {},
        )
        if task_id in self._subscribers:
            for q in self._subscribers[task_id]:
                try:
                    q.put_nowait(ev)
                except Exception:
                    pass

        for listener in self._global_listeners:
            try:
                listener(ev)
            except Exception:
                pass

        return ev

    def add_global_listener(self, callback: Callable[[TaskEvent], Any]) -> None:
        self._global_listeners.append(callback)


EVENT_BUS = TaskEventBus()
EventBus = TaskEventBus
