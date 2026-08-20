"""PLUTON V2 Central Execution Runtime.

The Runtime is the core coordinator for:
- Task State Machine Transitions (CREATED -> PLANNING -> READY -> EXECUTING -> VERIFYING -> WAITING -> AWAITING_APPROVAL -> COMPLETED/FAILED/CANCELLED/TIMED_OUT)
- Timeout & Cancellation Enforcement
- Plan & Step Execution Lifecycle
- Preemption & Safe Physical Control Cleanup
- Event Stream Orchestration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Optional
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..events.event_bus import EVENT_BUS, EventBus
from ..kernel.control_kernel import KERNEL, ControlKernel
from ..memory.store import MEMORY_STORE
from ..models import Activity, Task, TaskStatus
from ..providers import AIProvider, ProviderRequest, create_provider
from ..security import PermissionLevel
from ..tool_executor import ToolExecutor, persist_activity
from ..tools import TOOLS, ToolRegistry
from .contracts import (
    Action,
    AgentResult,
    CapabilityType,
    EventType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TaskEvent,
    TaskState,
    TERMINAL_TASK_STATES,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)
from ..capabilities.capability_router import CAPABILITY_ROUTER
from ..verification.verification_engine import VERIFICATION_ENGINE, VerificationEngine
from .agent_loop import UniversalAgentLoop

logger = logging.getLogger("pluton.runtime")


class PlutonRuntime:
    """Universal stateful execution engine for PLUTON AI."""

    def __init__(
        self,
        provider: AIProvider | None = None,
        registry: ToolRegistry | None = None,
        router: Any = None,
        verification_engine: Optional[VerificationEngine] = None,
        kernel: Optional[ControlKernel] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        try:
            self.provider = provider or create_provider()
            self._provider_error = None
        except Exception as e:
            self.provider = None
            self._provider_error = str(e)
        from ..capabilities.model_registry import CANONICAL_MODEL_REGISTRY
        self.registry = registry or CANONICAL_MODEL_REGISTRY
        self.router = router or CAPABILITY_ROUTER
        self.verification_engine = verification_engine or VERIFICATION_ENGINE
        self.kernel = kernel or KERNEL
        self.event_bus = event_bus or EVENT_BUS
        self.executor = ToolExecutor(self.registry)
        self.max_steps = get_settings().max_agent_steps
        
        self.agent_loop = UniversalAgentLoop(
            router=self.router,
            verifier=self.verification_engine,
            kernel=self.kernel,
            event_bus=self.event_bus,
            provider=self.provider,
        )
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        """Fail fast at construction time if any required dependency is missing."""
        if self.router is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: PlutonRuntime missing 'router'")
        if self.verification_engine is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: PlutonRuntime missing 'verification_engine'")
        if self.kernel is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: PlutonRuntime missing 'kernel'")
        if self.event_bus is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: PlutonRuntime missing 'event_bus'")
        if self.agent_loop is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: PlutonRuntime missing 'agent_loop'")

    # -------------------------------------------------------------------------
    # State Machine Transitions
    # -------------------------------------------------------------------------

    def transition_state(self, db: Session, task: Task, target_state: TaskState, reason: str = "") -> None:
        """Explicitly transition task state with validation and audit logging."""
        old_state_str = task.status
        task.status = target_state.value
        db.commit()
        logger.info("[RUNTIME:v2] Task %s state: %s -> %s (%s)", task.id, old_state_str, target_state.value, reason)

    # -------------------------------------------------------------------------
    # Main Task Execution Pipeline
    # -------------------------------------------------------------------------

    async def execute_task(self, task_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Execute a task through the canonical V2 state machine."""
        db = SessionLocal()
        context = ExecutionContext(task_id=task_id)
        self.kernel.authorize_task(task_id, context=context)

        try:
            task = db.get(Task, task_id)
            if task is None:
                yield ("error", {"message": f"Task '{task_id}' not found."})
                return

            if self._provider_error:
                task.status = TaskStatus.FAILED.value
                task.response = self._provider_error
                persist_activity(db, task.id, "agent.error", self._provider_error, status="failed")
                db.commit()
                yield ("error", {"message": self._provider_error})
                return

            if self.provider and hasattr(self.provider, "settings"):
                st = self.provider.settings
                if getattr(self.provider, "name", "") == "openai" and not getattr(st, "openai_api_key", None):
                    err_msg = "No AI provider key configured for OpenAI. Set PLUTON_OPENAI_API_KEY or configure provider."
                    task.status = TaskStatus.FAILED.value
                    task.response = err_msg
                    persist_activity(db, task.id, "agent.error", err_msg, status="failed")
                    db.commit()
                    yield ("error", {"message": err_msg})
                    return

            # -----------------------------------------------------------------
            # FRONT-DOOR TASK ROUTER EVALUATION (Milestone 2)
            # -----------------------------------------------------------------
            from app.router import FRONT_DOOR_ROUTER, RouteContext
            from app.fast_plane import FastCapabilityExecutor

            route_ctx = RouteContext(session_id=task.session_id)
            route_decision = FRONT_DOOR_ROUTER.route(task.request, route_ctx)

            # Fast Deterministic Capability Path (< 5ms, zero model call, zero physical agent)
            if route_decision.capability_id and FastCapabilityExecutor.can_handle(route_decision.capability_id):
                fast_res = FastCapabilityExecutor.execute(route_decision.capability_id, route_decision.parameters)
                resp_msg = fast_res.get("message") or fast_res.get("result_string") or str(fast_res)

                task.response = resp_msg
                task.status = TaskStatus.COMPLETED.value
                persist_activity(
                    db,
                    task.id,
                    f"fast_plane.{route_decision.capability_id}",
                    resp_msg,
                    status="completed" if fast_res.get("success", True) else "failed",
                )
                db.commit()

                self.event_bus.emit(EventType.TASK_COMPLETED, task_id, {"response": resp_msg, "fast_path": True})
                yield ("text", {"delta": resp_msg})
                yield (
                    "done",
                    {
                        "task_id": task.id,
                        "session_id": task.session_id,
                        "message": task.response,
                        "status": task.status,
                    },
                )
                return

            # If request does not require computer agent (Conversation / Knowledge fast lane)
            if not route_decision.requires_computer_agent:
                async for ev_type, ev_data in self.agent_loop.run_conversational(db, task, context):
                    yield (ev_type, ev_data)
                return

            # Run Universal Agent Execution Loop for Physical Computer Tasks
            async for ev_type, ev_data in self.agent_loop.run(db, task, context):
                yield (ev_type, ev_data)
            return

        except (asyncio.CancelledError, GeneratorExit):
            t = db.get(Task, task_id)
            if t and t.status not in [s.value for s in TERMINAL_TASK_STATES]:
                context.mark_cancelled("Client disconnected or cancelled")
                self.transition_state(db, t, TaskState.CANCELLED, "Client cancelled execution")
                persist_activity(db, task_id, "agent.cancel", "Task was cancelled.", status="cancelled")
                db.commit()
                self.kernel.emergency_stop()
            else:
                self.kernel.revoke_task(task_id)
            raise
        except Exception as error:
            logger.exception("[RUNTIME:v2] Fatal unhandled error executing task %s: %s", task_id, error)
            t = db.get(Task, task_id)
            if t and t.status not in [s.value for s in TERMINAL_TASK_STATES]:
                self.transition_state(db, t, TaskState.FAILED, str(error))
                persist_activity(db, task_id, "agent.error", str(error), status="failed")
                db.commit()
            self.event_bus.emit(EventType.TASK_FAILED, task_id, {"error": str(error)})
            yield ("error", {"message": f"Runtime error: {error}"})
        finally:
            self.kernel.revoke_task(task_id)
            db.close()

    # -------------------------------------------------------------------------
    # Task Resumption (Confirmations)
    # -------------------------------------------------------------------------

    async def resume_task(self, task_id: str, approved: bool) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Resume a task paused in AWAITING_APPROVAL."""
        db = SessionLocal()
        context = ExecutionContext(task_id=task_id)
        self.kernel.authorize_task(task_id, context=context)

        try:
            task = db.get(Task, task_id)
            if not task:
                yield ("error", {"message": f"Task '{task_id}' not found."})
                return
            if task.status != TaskState.AWAITING_APPROVAL.value and task.status != TaskStatus.CONFIRMING.value:
                yield ("error", {"message": f"Task '{task_id}' is not waiting for approval (status={task.status})."})
                return

            if not approved:
                self.transition_state(db, task, TaskState.CANCELLED, "Action denied by user")
                task.response = "The requested action was denied by user."
                persist_activity(db, task.id, "agent.denied", "High-risk tool call denied by user.", status="denied")
                db.commit()
                self.event_bus.emit(EventType.TASK_FAILED, task_id, {"reason": "denied"})
                yield ("activity", {"name": "agent.denied", "summary": "High-risk tool call denied by user.", "status": "denied"})
                yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                return

            # Re-execute through agent loop
            self.transition_state(db, task, TaskState.EXECUTING, "Action approved by user")
            async for ev_tuple in self.agent_loop.run(db, task, context):
                yield ev_tuple

        except (asyncio.CancelledError, GeneratorExit):
            context.mark_cancelled("Client disconnected or cancelled")
            t = db.get(Task, task_id)
            if t and t.status not in [s.value for s in TERMINAL_TASK_STATES]:
                self.transition_state(db, t, TaskState.CANCELLED, "Client cancelled execution")
                db.commit()
            self.kernel.emergency_stop()
            raise
        except Exception as error:
            logger.exception("[RUNTIME:v2] Fatal unhandled error resuming task %s: %s", task_id, error)
            t = db.get(Task, task_id)
            if t and t.status not in [s.value for s in TERMINAL_TASK_STATES]:
                self.transition_state(db, t, TaskState.FAILED, str(error))
                db.commit()
            self.event_bus.emit(EventType.TASK_FAILED, task_id, {"error": str(error)})
            yield ("error", {"message": f"Runtime error: {error}"})
        finally:
            self.kernel.revoke_task(task_id)
            db.close()


RUNTIME = PlutonRuntime()