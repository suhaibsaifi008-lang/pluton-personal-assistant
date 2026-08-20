"""
PLUTON V2 — Typed Bounded Planner Context & Context Assembler.
Selectively assembles conversation, task, world-state, capability, memory, and failure context
for the Semantic Planner without prompt bloat or sensitive data exposure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Optional

from .capability_schema import CapabilityRegistry


@dataclass
class ConversationContext:
    """Bounded conversation history and turn state."""
    recent_turns: list[dict[str, str]] = field(default_factory=list) # max 6 turns
    unresolved_references: list[str] = field(default_factory=list)
    last_user_goal: Optional[str] = None
    last_assistant_action: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recent_turns": self.recent_turns,
            "unresolved_references": self.unresolved_references,
            "last_user_goal": self.last_user_goal,
            "last_assistant_action": self.last_assistant_action,
        }


@dataclass
class TaskContext:
    """Current active task, execution state, and completed step outcomes."""
    task_id: str = ""
    task_description: str = ""
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0
    last_step_result: Optional[dict[str, Any]] = None
    accumulated_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "completed_steps": self.completed_steps,
            "current_step_index": self.current_step_index,
            "last_step_result": self.last_step_result,
            "accumulated_artifacts": self.accumulated_artifacts,
        }


@dataclass
class WorldContext:
    """Salient desktop, browser, and filesystem state relevant to the current request."""
    active_application: Optional[str] = None
    focused_window_title: Optional[str] = None
    open_windows: list[str] = field(default_factory=list) # max 10
    active_browser: Optional[str] = None
    open_browser_tabs: list[dict[str, str]] = field(default_factory=list) # max 10: [{"url": "...", "title": "..."}]
    recent_created_files: list[str] = field(default_factory=list) # max 5
    recent_modified_files: list[str] = field(default_factory=list) # max 5
    working_directory: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_application": self.active_application,
            "focused_window_title": self.focused_window_title,
            "open_windows": self.open_windows[:10],
            "active_browser": self.active_browser,
            "open_browser_tabs": self.open_browser_tabs[:10],
            "recent_created_files": self.recent_created_files[:5],
            "recent_modified_files": self.recent_modified_files[:5],
            "working_directory": self.working_directory,
        }


@dataclass
class MemoryContext:
    """Selective task-relevant user preferences and historical facts."""
    relevant_facts: list[str] = field(default_factory=list)
    user_preferences: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant_facts": self.relevant_facts[:5],
            "user_preferences": self.user_preferences,
        }


@dataclass
class FailureContext:
    """Context from previous execution failures for dynamic replanning."""
    failed_step_index: Optional[int] = None
    failure_reason: Optional[str] = None
    failure_classification: Optional[str] = None
    invalidated_targets: list[str] = field(default_factory=list)
    attempted_strategies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failed_step_index": self.failed_step_index,
            "failure_reason": self.failure_reason,
            "failure_classification": self.failure_classification,
            "invalidated_targets": self.invalidated_targets,
            "attempted_strategies": self.attempted_strategies,
        }


@dataclass
class PlannerContext:
    """Canonical typed, bounded context package assembled for the Semantic Planner."""
    conversation: ConversationContext = field(default_factory=ConversationContext)
    task: TaskContext = field(default_factory=TaskContext)
    world: WorldContext = field(default_factory=WorldContext)
    memory: MemoryContext = field(default_factory=MemoryContext)
    failure: FailureContext = field(default_factory=FailureContext)

    def to_dict(self) -> dict[str, Any]:
        d = {}
        conv = self.conversation.to_dict()
        if conv["recent_turns"] or conv["last_user_goal"]:
            d["conversation"] = conv
        t_dict = self.task.to_dict()
        if t_dict["task_id"] or t_dict["completed_steps"]:
            d["task"] = t_dict
        w_dict = self.world.to_dict()
        if any(w_dict.values()):
            d["world"] = {k: v for k, v in w_dict.items() if v}
        m_dict = self.memory.to_dict()
        if m_dict["relevant_facts"] or m_dict["user_preferences"]:
            d["memory"] = m_dict
        if self.failure.failure_reason:
            d["failure"] = self.failure.to_dict()
        return d


class ContextAssembler:
    """
    Selectively and deterministically extracts and bounds relevant context
    for semantic planning from raw runtime state, session history, and world state.
    """

    @classmethod
    def assemble(
        cls,
        request_text: str,
        context_metadata: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
        task_state: dict[str, Any] | None = None,
        failure_state: dict[str, Any] | None = None,
    ) -> PlannerContext:
        ctx_meta = context_metadata or {}
        hist = history or []
        t_state = task_state or {}
        f_state = failure_state or {}

        # 1. Bounded Conversation Context
        conv_ctx = ConversationContext(
            recent_turns=hist[-6:] if hist else [],
            last_user_goal=hist[-2].get("content") if len(hist) >= 2 and hist[-2].get("role") == "user" else None,
            last_assistant_action=hist[-1].get("content") if hist and hist[-1].get("role") == "assistant" else None,
        )

        # 2. Task Context
        completed = t_state.get("completed_steps", [])
        task_ctx = TaskContext(
            task_id=t_state.get("task_id", ""),
            task_description=t_state.get("task_description", ""),
            completed_steps=completed[-5:] if completed else [],
            current_step_index=t_state.get("current_step_index", 0),
            last_step_result=completed[-1] if completed else None,
            accumulated_artifacts=t_state.get("accumulated_artifacts", [])[-5:],
        )

        # 3. World Context (Clean, bounded, generic)
        world_ctx = WorldContext(
            active_application=ctx_meta.get("active_window") or ctx_meta.get("active_application"),
            focused_window_title=ctx_meta.get("focused_window_title"),
            open_windows=ctx_meta.get("open_windows", [])[:10],
            active_browser=ctx_meta.get("active_browser"),
            open_browser_tabs=ctx_meta.get("open_browser_tabs", [])[:10],
            recent_created_files=ctx_meta.get("recent_files", [])[:5],
            recent_modified_files=ctx_meta.get("recent_modified_files", [])[:5],
            working_directory=ctx_meta.get("working_directory", ""),
        )

        # 4. Memory Context
        memory_ctx = MemoryContext(
            relevant_facts=ctx_meta.get("memory_facts", [])[:5],
            user_preferences=ctx_meta.get("user_preferences", {}),
        )

        # 5. Failure Context (for replanning)
        failure_ctx = FailureContext(
            failed_step_index=f_state.get("failed_step_index"),
            failure_reason=f_state.get("failure_reason"),
            failure_classification=f_state.get("failure_classification"),
            invalidated_targets=f_state.get("invalidated_targets", []),
            attempted_strategies=f_state.get("attempted_strategies", []),
        )

        return PlannerContext(
            conversation=conv_ctx,
            task=task_ctx,
            world=world_ctx,
            memory=memory_ctx,
            failure=failure_ctx,
        )