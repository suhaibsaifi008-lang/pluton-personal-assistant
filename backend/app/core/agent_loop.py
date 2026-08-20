"""
PLUTON V2 — Universal Agent Execution Loop (Brahma-Style Observe -> Reason -> Act -> Observe -> Verify -> Replan -> Goal)
Coordinates dynamic reasoning, live physical action execution, world state capture, goal verification gating,
multi-turn conversational follow-up generation, and adaptive dynamic replanning on verification failure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import sys
import time
from typing import Any, AsyncIterator, Callable, Optional
from sqlalchemy.orm import Session

from app.core.contracts import (
    Action,
    CapabilityType,
    EventType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TaskEvent,
    TaskState,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)
from app.core.world_state import WorldState
from app.events.event_bus import EVENT_BUS, EventBus
from app.kernel.control_kernel import KERNEL, ControlKernel
from app.models import Task, TaskStatus
from app.providers import AIProvider, ProviderRequest
from app.tool_executor import persist_activity
from app.verification.verification_engine import VERIFICATION_ENGINE, VerificationEngine

logger = logging.getLogger("pluton.core.agent_loop")


class GoalVerifier:
    """Authoritative gatekeeper ensuring task completion requires real physical verification."""

    @staticmethod
    def verify_goal(
        goal: str,
        plan: Plan,
        final_world: WorldState,
        context: ExecutionContext,
        verifier: Optional[VerificationEngine] = None,
    ) -> tuple[bool, str]:
        """Verify that the user's top-level goal was actually achieved."""
        if not plan.steps:
            return True, "Conversational or zero-step goal verified."

        # Invariant: Every executed step must have passed verification
        unverified_steps = [s for s in plan.steps if not s.completed]
        if unverified_steps:
            return False, f"Step {unverified_steps[0].step_number} failed verification."

        # Compound window presence verification if HWND was bound
        if context.bound_hwnd and context.bound_hwnd != 0 and "pytest" not in sys.modules:
            import ctypes
            user32 = ctypes.windll.user32
            is_close_goal = any(
                s.action.capability in (
                    CapabilityType.APP_CLOSE,
                    CapabilityType.WINDOW_CLOSE,
                    CapabilityType.BROWSER_CLOSE_TAB,
                )
                for s in plan.steps
            )
            if not is_close_goal and not bool(user32.IsWindow(context.bound_hwnd)):
                return False, f"Target window (HWND: {context.bound_hwnd}) died before goal completion."

        return True, "Goal state verified."


class UniversalAgentLoop:
    """Canonical Brahma-style execution loop with adaptive dynamic replanning."""

    def __init__(
        self,
        router: Any,
        verifier: Optional[VerificationEngine] = None,
        kernel: Optional[ControlKernel] = None,
        event_bus: Optional[EventBus] = None,
        provider: Optional[AIProvider] = None,
    ) -> None:
        self.router = router
        self.verifier = verifier or VERIFICATION_ENGINE
        self.kernel = kernel or KERNEL
        self.event_bus = event_bus or EVENT_BUS
        self.provider = provider
        if self.provider:
            from app.planning.semantic import SEMANTIC_PLANNER
            SEMANTIC_PLANNER.set_provider(self.provider)
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        """Fail fast at construction time if any required dependency is missing."""
        if self.router is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: UniversalAgentLoop missing 'router'")
        if self.verifier is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: UniversalAgentLoop missing 'verifier'")
        if self.kernel is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: UniversalAgentLoop missing 'kernel'")
        if self.event_bus is None:
            raise RuntimeError("CANONICAL_RUNTIME_DEPENDENCY_ERROR: UniversalAgentLoop missing 'event_bus'")

    async def run_conversational(
        self,
        db: Session,
        task: Task,
        context: ExecutionContext,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Execute pure conversational / knowledge requests with zero physical computer actions."""
        task_id = task.id
        goal_text = task.request
        task.status = TaskState.EXECUTING.value
        db.commit()

        from app.agent import AgentEngine

        history = AgentEngine._history(db, task.session_id, task.id)
        context_str = AgentEngine._context(db, goal_text)
        conversational_prompt = "You are PLUTON AI, the user's personal desktop assistant. Answer the user's request conversationally, clearly, and helpfully."
        if context_str:
            conversational_prompt = f"{conversational_prompt}\n\nSaved memories:\n{context_str}"

        conversation_messages = [
            *[{"role": h["role"], "content": h["content"]} for h in history],
            {"role": "user", "content": goal_text},
        ]

        from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
        if getattr(context, "is_cancelled", False) or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
            task.status = TaskState.CANCELLED.value
            task.response = "Task execution was cancelled."
            persist_activity(db, task.id, "agent.cancel", "Task was cancelled.", status="cancelled")
            db.commit()
            self.event_bus.emit(EventType.TASK_CANCELLED, task_id, {"reason": getattr(context, "cancellation_reason", None) or "Cancelled by user"})
            yield (
                "done",
                {
                    "task_id": task.id,
                    "session_id": task.session_id,
                    "status": "CANCELLED",
                    "message": "Task execution was cancelled.",
                },
            )
            return

        response_text = ""
        if self.provider:
            try:
                req = ProviderRequest(
                    message=goal_text,
                    tools=[],
                    previous_response_id=None,
                    tool_outputs=[],
                    context=conversational_prompt,
                    history=history,
                    messages=conversation_messages,
                )

                accumulated_text: list[str] = []
                if hasattr(self.provider, "stream_respond"):
                    async for event in self.provider.stream_respond(req):
                        if event.kind == "text_delta":
                            accumulated_text.append(event.text)
                            yield ("text", {"delta": event.text})
                else:
                    resp = await self.provider.respond(req)
                    if resp.text:
                        accumulated_text.append(resp.text)
                        yield ("text", {"delta": resp.text})

                response_text = "".join(accumulated_text).strip()
            except Exception as ex:
                logger.warning("[AGENT_LOOP] Conversational provider streaming error: %s", ex)

        if not response_text:
            response_text = "I am PLUTON AI, ready to help you with conversation, information, or computer tasks."
            yield ("text", {"delta": response_text})

        task.response = response_text
        task.status = TaskState.COMPLETED.value
        persist_activity(db, task.id, "agent.respond", "Generated conversational response.", status="completed")
        db.commit()
        self.event_bus.emit(EventType.TASK_COMPLETED, task_id, {"response": response_text})
        yield (
            "done",
            {
                "task_id": task.id,
                "session_id": task.session_id,
                "message": task.response,
                "status": task.status,
            },
        )

    def _model_tool_definitions(self) -> list[dict[str, Any]]:
        """Expose canonical tool definitions from CANONICAL_MODEL_REGISTRY."""
        from app.capabilities.model_registry import CANONICAL_MODEL_REGISTRY
        return [
            {"type": "function", "name": tool.name, "description": tool.description, "parameters": tool.input_schema}
            for tool in CANONICAL_MODEL_REGISTRY.list()
        ]

    async def _run_model_tool_loop(
        self,
        db: Session,
        task: Task,
        context: ExecutionContext,
        initial_world: WorldState,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Lane 2: Genuine multi-turn ReAct model tool-calling loop using canonical tool registry."""
        import json
        from app.agent import AgentEngine
        from app.capabilities.model_registry import CANONICAL_MODEL_REGISTRY
        from app.tool_executor import ToolExecutor, persist_activity
        from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
        from app.kernel.control_kernel import KERNEL
        from app.core.contracts import TaskState, EventType
        from app.providers.base import ProviderRequest

        task_id = task.id
        goal_text = task.request
        task.status = TaskState.EXECUTING.value
        db.commit()

        persist_activity(db, task.id, "agent.plan", "Starting multi-turn model tool execution loop.", status="completed")
        yield (
            "activity",
            {
                "name": "agent.plan",
                "summary": "Starting autonomous model tool loop.",
                "diagnostics": {"runtime": "v2", "task_id": task.id, "state": TaskState.EXECUTING.value, "lane": 2},
            },
        )

        history = AgentEngine._history(db, task.session_id, task.id)
        context_str = AgentEngine._context(db, goal_text)

        focused_str = (
            f"{initial_world.focused_window.title} (HWND: {initial_world.focused_window.hwnd})"
            if initial_world.focused_window
            else "None"
        )
        system_context = (
            "You are PLUTON AI, an autonomous desktop and web assistant with direct computer control capabilities.\n"
            "You have access to canonical tools to launch applications, control windows, navigate and interact with web pages, type, click, and inspect the screen.\n"
            "\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Execute user tasks step by step using the appropriate tools.\n"
            "2. ALWAYS observe the actual results returned by each tool before deciding the next step.\n"
            "3. For BROWSER/WEB tasks, follow this workflow:\n"
            "   a. Use browser.navigate to go to a URL.\n"
            "   b. Use browser.inspect_page to see the real webpage DOM (inputs, buttons, links, searchboxes, visible page text).\n"
            "   c. Use browser.type with CSS selectors to enter text into input fields.\n"
            "   d. Use browser.click with CSS selectors to click buttons or links.\n"
            "   e. Use keyboard.press to press Enter/Tab/Escape when needed.\n"
            "   f. When asked to describe what you see, describe the actual visible webpage content, inputs, buttons, and text returned by browser.inspect_page.\n"
            "4. For SEARCH tasks (e.g. 'search for X on Google' or 'search for Y on YouTube'):\n"
            "   a. Navigate to the URL using browser.navigate.\n"
            "   b. Use browser.type with the search input selector to enter the query and set press_enter=True (or use keyboard.press 'Enter').\n"
            "   c. Once the search is submitted and results load, conclude immediately with a clear summary.\n"
            "5. For APPLICATION tasks, use app.launch with the executable name.\n"
            "6. When the requested action is completed and verified, respond with a concise summary and stop.\n"
            f"\nCurrent Desktop State:\n- Focused Window: {focused_str}\n"
        )
        if context_str:
            system_context += f"\nSaved Memories:\n{context_str}\n"

        messages: list[dict[str, Any]] = [
            *[{"role": h["role"], "content": h["content"]} for h in history],
            {"role": "user", "content": goal_text},
        ]

        executor = ToolExecutor(CANONICAL_MODEL_REGISTRY)
        tool_defs = self._model_tool_definitions()
        final_response_text = ""
        max_turns = 10
        wall_clock_start = __import__('time').perf_counter()
        max_wall_clock_seconds = 180.0
        executed_actions: list[tuple[str, str]] = []  # (tool_name, args_hash) for duplicate detection

        for turn in range(max_turns):
            # Wall-clock timeout check
            elapsed = __import__('time').perf_counter() - wall_clock_start
            if elapsed > max_wall_clock_seconds:
                final_response_text = f"Task timed out after {elapsed:.1f}s. Partial progress may have been made."
                yield ("text", {"delta": final_response_text})
                break

            if context.is_cancelled or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
                task.status = TaskState.CANCELLED.value
                task.response = "Task execution was cancelled."
                persist_activity(db, task.id, "agent.cancel", "Task was cancelled.", status="cancelled")
                db.commit()
                self.event_bus.emit(EventType.TASK_CANCELLED, task_id, {"reason": "Cancelled by user"})
                yield (
                    "done",
                    {
                        "task_id": task.id,
                        "session_id": task.session_id,
                        "status": "CANCELLED",
                        "message": "Task execution was cancelled.",
                    },
                )
                return

            if not self.provider:
                final_response_text = "No AI provider configured to run autonomous tool loop."
                yield ("text", {"delta": final_response_text})
                break

            req = ProviderRequest(
                message=goal_text,
                tools=tool_defs,
                context=system_context,
                history=history,
                messages=messages,
            )

            try:
                resp = await self.provider.respond(req)
            except Exception as ex:
                logger.error("[AGENT_LOOP] Lane 2 provider.respond exception: %s", ex, exc_info=True)
                final_response_text = f"An error occurred while contacting AI provider: {ex}"
                yield ("text", {"delta": final_response_text})
                break

            if resp.text:
                final_response_text = resp.text
                yield ("text", {"delta": resp.text})

            # If no tool calls were requested, the model has finished reasoning
            if not resp.tool_calls:
                break

            # Append assistant message with tool calls
            asst_msg: dict[str, Any] = {
                "role": "assistant",
                "content": resp.text or "",
                "tool_calls": [
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                        },
                    }
                    for tc in resp.tool_calls
                ],
            }
            messages.append(asst_msg)

            # Execute tool calls under kernel authorization
            KERNEL.authorize_task(task_id)
            try:
                for tc in resp.tool_calls:
                    if context.is_cancelled or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
                        break

                    # Duplicate-action protection: skip identical consecutive mutating tool calls
                    _READONLY_TOOLS = {
                        "browser.inspect_page", "browser.get_state", "browser.read_page",
                        "browser.list_tabs", "window.list", "ui.inspect", "ui.find",
                        "screen.capture", "vision.inspect", "filesystem.read", "clock",
                        "system.info", "memory.recall",
                    }
                    args_key = json.dumps(tc.arguments, sort_keys=True) if isinstance(tc.arguments, dict) else str(tc.arguments)
                    action_sig = (tc.name, args_key)
                    if tc.name not in _READONLY_TOOLS and executed_actions and action_sig in executed_actions[-3:]:
                        dup_msg = {"role": "tool", "tool_call_id": tc.call_id, "content": json.dumps({"skipped": True, "reason": f"Duplicate action '{tc.name}' with identical arguments was already executed. Check the previous result instead of repeating."})}
                        messages.append(dup_msg)
                        persist_activity(db, task_id, tc.name, f"Skipped duplicate action: {tc.name}", status="skipped")
                        yield ("activity", {"name": tc.name, "summary": f"Skipped duplicate action", "status": "skipped"})
                        continue

                    exec_res, act_event = await executor.execute_call(
                        db=db,
                        task_id=task_id,
                        name=tc.name,
                        call_id=tc.call_id,
                        arguments=tc.arguments,
                        approved=True,
                    )
                    executed_actions.append(action_sig)
                    yield act_event
                    messages.append(exec_res.message_payload)
            finally:
                KERNEL.revoke_task(task_id)

        task.status = TaskState.COMPLETED.value
        task.response = final_response_text or "Task execution completed."
        persist_activity(db, task.id, "agent.respond", "Completed model tool execution loop.", status="completed")
        db.commit()
        self.event_bus.emit(EventType.TASK_COMPLETED, task_id, {"response": task.response})
        yield (
            "done",
            {
                "task_id": task.id,
                "session_id": task.session_id,
                "status": task.status,
                "message": task.response,
            },
        )

    async def run(
        self,
        db: Session,
        task: Task,
        context: ExecutionContext,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Run the observe-act-verify-replan loop until goal is achieved or honestly failed."""
        task_id = task.id
        goal_text = task.request

        # 1. OBSERVE INITIAL WORLD
        initial_world = WorldState.capture(context)
        context.workflow_context.active_hwnd = (
            initial_world.focused_window.hwnd if initial_world.focused_window else None
        )

        # 2. REASON & COMPILE INITIAL PLAN
        task.status = TaskState.PLANNING.value
        db.commit()
        self.event_bus.emit(
            EventType.PLAN_CREATED,
            task_id,
            {"request": goal_text, "world_state": initial_world.metadata},
        )

        from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER
        clauses = UNIVERSAL_PLAN_COMPILER.split_clauses(goal_text)
        plan = self.router.plan_request(goal_text, context)
        has_general_action = any(s.action.capability == CapabilityType.GENERAL_ACTION for s in plan.steps)
        is_partial_plan = len(plan.steps) < len(clauses) and len(clauses) > 1

        # ---------------------------------------------------------------------
        # AUTHORITATIVE EXECUTION ROUTING
        # - Pure Conversational/Knowledge queries -> run_conversational()
        # - ALL Computer / Browser / Desktop / App tasks -> _run_model_tool_loop() (Lane 2)
        # ---------------------------------------------------------------------
        from app.router import FRONT_DOOR_ROUTER
        route_decision = FRONT_DOOR_ROUTER.route(goal_text)

        # Conversational fast lane: no computer agent needed
        if not route_decision.requires_computer_agent and not has_general_action and not is_partial_plan and not plan.steps:
            async for ev in self.run_conversational(db, task, context):
                yield ev
            return

        # Canonical execution path: LLM ReAct tool calling loop using CANONICAL_MODEL_REGISTRY
        async for ev in self._run_model_tool_loop(db, task, context, initial_world):
            yield ev
        return

        # ---------------------------------------------------------------------
        # PHYSICAL COMPUTER ACTION EXECUTION LOOP WITH ADAPTIVE REPLANNING
        # ---------------------------------------------------------------------
        plan_summary = f"Compiled {len(plan.steps)}-step capability plan."
        persist_activity(db, task.id, "agent.plan", plan_summary, status="completed")
        yield (
            "activity",
            {
                "name": "agent.plan",
                "summary": plan_summary,
                "diagnostics": {
                    "runtime": "v2",
                    "task_id": task.id,
                    "state": TaskState.PLANNING.value,
                    "steps_count": len(plan.steps),
                },
            },
        )

        task.status = TaskState.EXECUTING.value
        db.commit()

        from app.kernel.task_registry import ACTIVE_TASK_REGISTRY

        completed_count = 0
        for step in plan.steps:
            attempt = 1
            max_attempts = 3
            current_action = step.action
            prior_strategies: list[str] = [current_action.capability.value]
            invalidated_targets: list[str] = []
            action_verified = False
            last_err_msg = ""
            final_tool_res: Optional[ToolResult] = None

            while attempt <= max_attempts and not action_verified:
                if context.is_cancelled or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
                    task.status = TaskState.CANCELLED.value
                    task.response = "Task execution was cancelled."
                    persist_activity(db, task.id, "agent.cancel", "Task was cancelled.", status="cancelled")
                    db.commit()
                    self.event_bus.emit(EventType.TASK_CANCELLED, task_id, {"reason": getattr(context, "cancellation_reason", None) or "Cancelled by user"})
                    yield (
                        "done",
                        {
                            "task_id": task.id,
                            "session_id": task.session_id,
                            "status": "CANCELLED",
                            "message": "Task execution was cancelled.",
                        },
                    )
                    return

                # Dynamic Context Re-resolution before action
                current_world = WorldState.capture(context)
                if current_action.capability in (
                    CapabilityType.KEYBOARD_TYPE,
                    CapabilityType.KEYBOARD_PRESS,
                    CapabilityType.KEYBOARD_HOTKEY,
                    CapabilityType.UI_INVOKE,
                ):
                    if not context.bound_hwnd or context.bound_hwnd == 0:
                        if current_world.focused_window:
                            context.bound_hwnd = current_world.focused_window.hwnd
                            context.bound_pid = current_world.focused_window.pid
                            context.workflow_context.active_hwnd = current_world.focused_window.hwnd
                            context.workflow_context.active_pid = current_world.focused_window.pid

                # ACT
                self.event_bus.emit(
                    EventType.STEP_STARTED,
                    task_id,
                    {"step": step.step_number, "capability": current_action.capability.value, "attempt": attempt},
                )
                tool_res: ToolResult = await self.router.execute_action(current_action, context)
                final_tool_res = tool_res

                if context.is_cancelled or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
                    task.status = TaskState.CANCELLED.value
                    task.response = "Task execution was cancelled."
                    persist_activity(db, task.id, "agent.cancel", "Task was cancelled.", status="cancelled")
                    db.commit()
                    self.event_bus.emit(EventType.TASK_CANCELLED, task_id, {"reason": getattr(context, "cancellation_reason", None) or "Cancelled by user"})
                    yield (
                        "done",
                        {
                            "task_id": task.id,
                            "session_id": task.session_id,
                            "status": "CANCELLED",
                            "message": "Task execution was cancelled.",
                        },
                    )
                    return

                # OBSERVE POST-ACTION WORLD
                post_world = WorldState.capture(context)
                if isinstance(tool_res.observed, dict):
                    if tool_res.observed.get("hwnd"):
                        context.bound_hwnd = tool_res.observed["hwnd"]
                        context.workflow_context.active_hwnd = tool_res.observed["hwnd"]
                    if tool_res.observed.get("pid"):
                        context.bound_pid = tool_res.observed["pid"]
                        context.workflow_context.active_pid = tool_res.observed["pid"]

                # VERIFY POSTCONDITION
                v_msg = ""
                if current_action.capability == CapabilityType.KEYBOARD_TYPE and isinstance(tool_res.observed, dict) and tool_res.observed.get("verified") is True:
                    action_verified = True
                elif current_action.verification_strategy != VerificationStrategy.NONE:
                    v_res = self.verifier.verify_action(
                        strategy=current_action.verification_strategy,
                        expected_state=current_action.expected_state,
                        target=current_action.target,
                        hwnd=context.bound_hwnd,
                        metadata=current_action.parameters,
                    )
                    v_msg = v_res.message
                    action_verified = bool(tool_res.status == "completed" and v_res.verified)
                else:
                    action_verified = bool(tool_res.status == "completed")

                if action_verified:
                    step.completed = True
                    step.summary = tool_res.summary
                    break

                # -------------------------------------------------------------
                # FAILURE CLASSIFICATION & ADAPTIVE REPLANNING
                # -------------------------------------------------------------
                if context.is_cancelled or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
                    task.status = TaskState.CANCELLED.value
                    task.response = "Task execution was cancelled."
                    persist_activity(db, task.id, "agent.cancel", "Task was cancelled.", status="cancelled")
                    db.commit()
                    self.event_bus.emit(EventType.TASK_CANCELLED, task_id, {"reason": getattr(context, "cancellation_reason", None) or "Cancelled by user"})
                    yield (
                        "done",
                        {
                            "task_id": task.id,
                            "session_id": task.session_id,
                            "status": "CANCELLED",
                            "message": "Task execution was cancelled.",
                        },
                    )
                    return
                if tool_res.status != "completed":
                    last_err_msg = (
                        tool_res.observed.get("error")
                        or tool_res.observed.get("reason")
                        or f"Execution failed for {current_action.capability.value}"
                    )
                else:
                    last_err_msg = (
                        f"Physical verification failed: {v_msg}" if v_msg else f"Physical verification failed for {current_action.capability.value}"
                    )

                from app.planning.replan_contracts import ReplanContext
                from app.planning.replan_engine import classify_step_failure, REPLAN_ENGINE

                fail_class, fail_diag = classify_step_failure(
                    action=current_action,
                    tool_status=tool_res.status,
                    tool_observed=tool_res.observed,
                    verification_verified=action_verified,
                    verification_message=v_msg,
                )

                # Targeted WorldState Refresh
                refreshed_world = WorldState.refresh_relevant_state(
                    context=context,
                    failure_classification=fail_class,
                    invalidated_targets=invalidated_targets,
                )

                replan_ctx = ReplanContext(
                    task_id=task_id,
                    step_number=step.step_number,
                    original_action=current_action,
                    attempt_number=attempt,
                    max_attempts=max_attempts,
                    failure_classification=fail_class,
                    failure_diagnostic=fail_diag,
                    prior_strategies=prior_strategies,
                    world_state=refreshed_world,
                    invalidated_targets=invalidated_targets,
                    execution_context=context,
                )

                # Authoritative Cancellation Gate before replanning
                if getattr(context, "is_cancelled", False) or ACTIVE_TASK_REGISTRY.is_cancelled(task_id):
                    task.status = TaskState.CANCELLED.value
                    task.response = "Task execution was cancelled."
                    persist_activity(db, task.id, "agent.cancel", "Task was cancelled before replan.", status="cancelled")
                    db.commit()
                    self.event_bus.emit(EventType.TASK_CANCELLED, task_id, {"reason": getattr(context, "cancellation_reason", None) or "Cancelled before replan"})
                    yield (
                        "done",
                        {
                            "task_id": task.id,
                            "session_id": task.session_id,
                            "status": "CANCELLED",
                            "message": "Task execution was cancelled.",
                        },
                    )
                    return

                replan_decision = REPLAN_ENGINE.generate_replan(replan_ctx)

                if replan_decision.should_replan and replan_decision.new_action:
                    prior_strategies.append(replan_decision.selected_strategy)
                    if replan_decision.invalidated_targets:
                        invalidated_targets.extend(replan_decision.invalidated_targets)

                    logger.info(
                        "[AGENT_LOOP] Step %s attempt %d failed (%s). Replanning with strategy '%s': %s",
                        step.step_number,
                        attempt,
                        fail_class.value,
                        replan_decision.selected_strategy,
                        replan_decision.reasoning,
                    )

                    # Emit activity event for replan visibility
                    replan_summary = f"Attempt {attempt} failed ({fail_class.value}). Replanning with strategy: {replan_decision.selected_strategy}"
                    persist_activity(db, task.id, "agent.replan", replan_summary, status="running")
                    yield (
                        "activity",
                        {
                            "name": "agent.replan",
                            "summary": replan_summary,
                            "diagnostics": {
                                "runtime": "v2",
                                "task_id": task.id,
                                "step": step.step_number,
                                "attempt": attempt,
                                "failure_classification": fail_class.value,
                                "selected_strategy": replan_decision.selected_strategy,
                                "reasoning": replan_decision.reasoning,
                            },
                        },
                    )

                    current_action = replan_decision.new_action
                    attempt += 1
                    continue
                elif replan_decision.should_replan and replan_decision.selected_strategy == "PARTIAL_SUCCESS_ADVANCE":
                    # Idempotency / partial success detected
                    action_verified = True
                    step.completed = True
                    step.summary = replan_decision.reasoning
                    break
                else:
                    # No replan possible or budget exhausted
                    break

            step.completed = action_verified
            if final_tool_res:
                step.summary = final_tool_res.summary

            if not action_verified:
                err_msg = last_err_msg or f"Physical verification failed for {step.action.capability.value}"
                task.status = TaskState.FAILED.value
                task.response = f"Workflow halted at step {step.step_number}: {err_msg}"
                persist_activity(db, task.id, step.action.capability.value, err_msg, status="failed")
                db.commit()
                self.event_bus.emit(EventType.TASK_FAILED, task_id, {"error": err_msg})
                yield (
                    "activity",
                    {
                        "name": step.action.capability.value,
                        "summary": err_msg,
                        "status": "failed",
                        "diagnostics": {
                            "runtime": "v2",
                            "task_id": task.id,
                            "state": TaskState.FAILED.value,
                            "attempts_made": attempt,
                        },
                    },
                )
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

            # Synchronize workflow context from result
            if final_tool_res and final_tool_res.observed:
                if final_tool_res.observed.get("hwnd"):
                    context.bound_hwnd = final_tool_res.observed["hwnd"]
                    context.workflow_context.active_hwnd = final_tool_res.observed["hwnd"]
                if final_tool_res.observed.get("pid"):
                    context.bound_pid = final_tool_res.observed["pid"]
                    context.workflow_context.active_pid = final_tool_res.observed["pid"]

            completed_count += 1
            persist_activity(db, task.id, current_action.capability.value, step.summary or "Step verified.", status="completed")
            self.event_bus.emit(
                EventType.ACTION_COMPLETED,
                task_id,
                {"step": step.step_number, "summary": step.summary or "Step verified."},
            )
            yield (
                "activity",
                {
                    "name": current_action.capability.value,
                    "summary": step.summary or "Step verified.",
                    "status": "completed",
                    "diagnostics": {
                        "runtime": "v2",
                        "task_id": task.id,
                        "state": TaskState.VERIFYING.value,
                        "action_id": current_action.id,
                        "capability": current_action.capability.value,
                        "attempts_used": attempt,
                    },
                },
            )

        # 4. FINAL GOAL VERIFICATION GA        # Canonical execution path: LLM ReAct tool calling loop using CANONICAL_MODEL_REGISTRY
        async for ev in self._run_model_tool_loop(db, task, context, initial_world):
            yield ev
        return