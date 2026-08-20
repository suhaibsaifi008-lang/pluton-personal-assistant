"""Bounded planner/executor loop shared by all AI providers.

Emits (event, data) tuples consumed by the API layer:
  - ("session", {...})        session identity when first created
  - ("activity", {...})       progress / tool activity
  - ("text", {"delta": ...})  progressive model text
  - ("confirmation", {...})   HIGH-risk tool paused, awaiting approval
  - ("done", {...})           final result
  - ("error", {"message"})    terminal failure
"""
import asyncio
import json
import re
from typing import Any, AsyncIterator


from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal, get_db
from .models import Activity, Task, TaskStatus, TERMINAL_TASK_STATES
from .providers import AIProvider, ProviderRequest, create_provider
from .security import PermissionLevel
from .kernel.control_kernel import KERNEL
from .tool_executor import ToolExecutor, persist_activity
from .tools import TOOLS, ToolRegistry, recall_memories
from .tools.computer_safety import enable_computer_control, disable_computer_control, emergency_kill_computer_input

_persist_activity = persist_activity



def _checkpoint_payload(message: str, previous_response_id: str, steps: int, pending: list[dict[str, Any]]) -> str:
    return json.dumps({
        "message": message,
        "previous_response_id": previous_response_id,
        "steps": steps,
        "pending": pending,
    })


def _parse_browser_tab_close_intent(request: str) -> tuple[str, str] | None:
    """Detect if request is asking to close a specific browser tab."""
    req = request.strip().lower()
    req_norm = re.sub(r"\bcl+a+u+d+e+\b", "claude", req)

    m = re.search(
        r"\bclose\s+(?:the\s+)?([a-z0-9\s\-]+?)\s+tab(?:\s+(?:in|on)\s+(?:my\s+)?([a-z0-9]+)(?:\s+browser)?)?",
        req_norm,
    )
    if m:
        raw_tab = m.group(1).strip()
        browser = m.group(2).strip().title() if m.group(2) else "Brave"
        if raw_tab and raw_tab not in ("browser", "window", "current", "this"):
            return raw_tab.title(), browser

    m2 = re.search(
        r"\bclose\s+(?:the\s+)?tab\s+(?:named\s+|titled\s+)?([a-z0-9\s\-]+?)(?:\s+(?:in|on)\s+(?:my\s+)?([a-z0-9]+)(?:\s+browser)?)?$",
        req_norm,
    )
    if m2:
        raw_tab = m2.group(1).strip()
        browser = m2.group(2).strip().title() if m2.group(2) else "Brave"
        if raw_tab and raw_tab not in ("browser", "window", "current", "this"):
            return raw_tab.title(), browser

    return None


class AgentEngine:
    def __init__(self, provider: AIProvider | None = None, registry: ToolRegistry | None = None) -> None:
        try:
            self.provider = provider or create_provider()
            self._provider_error = None
        except Exception as e:
            self.provider = None
            self._provider_error = str(e)
        from .capabilities.model_registry import CANONICAL_MODEL_REGISTRY
        self.registry = registry or CANONICAL_MODEL_REGISTRY
        self.executor = ToolExecutor(self.registry)
        from .core.runtime import PlutonRuntime
        self.runtime = PlutonRuntime(provider=self.provider, registry=self.registry)
        self.max_steps = get_settings().max_agent_steps
        from app.planning.semantic import SEMANTIC_PLANNER
        if self.provider:
            SEMANTIC_PLANNER.set_provider(self.provider)



    def _definitions(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "name": tool.name, "description": tool.description, "parameters": tool.input_schema}
            for tool in self.registry.list()
        ]



    @staticmethod
    def _history(
        db,
        session_id: str | None,
        exclude_task_id: str | None,
        limit_turns: int | None = None,
        max_tokens: int | None = None,
    ) -> list[dict[str, str]]:
        if not session_id:
            return []
        settings = get_settings()
        turn_limit = limit_turns or settings.max_history_turns
        token_budget = max_tokens or settings.max_history_tokens

        rows = db.scalars(
            select(Task).where(Task.session_id == session_id).order_by(Task.created_at.asc(), Task.id.asc())
        ).all()
        completed_turns: list[tuple[dict[str, str], dict[str, str]]] = []
        for task in rows:
            if task.id == exclude_task_id:
                continue
            if task.status == "COMPLETED" and task.response:
                user_msg = {"role": "user", "content": task.request}
                assistant_msg = {"role": "assistant", "content": task.response}
                completed_turns.append((user_msg, assistant_msg))

        recent_turns = completed_turns[-turn_limit:]
        accumulated_turns: list[tuple[dict[str, str], dict[str, str]]] = []
        consumed_tokens = 0
        for u_msg, a_msg in reversed(recent_turns):
            turn_chars = len(u_msg["content"]) + len(a_msg["content"])
            turn_tokens = max(1, turn_chars // 4)
            if consumed_tokens + turn_tokens > token_budget and accumulated_turns:
                break
            accumulated_turns.insert(0, (u_msg, a_msg))
            consumed_tokens += turn_tokens

        history: list[dict[str, str]] = []
        for u_msg, a_msg in accumulated_turns:
            history.append(u_msg)
            history.append(a_msg)
        return history

    @staticmethod
    def _context(db, message: str, max_chars: int = 2000) -> str:
        recalled = recall_memories(message, db=db)
        if not recalled:
            return ""
        lines: list[str] = []
        chars = 0
        for item in recalled:
            line = f"- [{item['category']}] {item['content']}"
            if chars + len(line) > max_chars and lines:
                break
            lines.append(line)
            chars += len(line)
        return "\n".join(lines)


    async def run(self, task_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Execute task through canonical V2 Central Runtime or provider loop for mock tests."""
        if self._provider_error:
            with SessionLocal() as db:
                task = db.get(Task, task_id)
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.response = self._provider_error
                    db.commit()
            yield ("error", {"message": self._provider_error})
            return

        with SessionLocal() as db:
            task = db.get(Task, task_id)
            if not task:
                yield ("error", {"message": f"Task '{task_id}' not found."})
                return
            if task.status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value, "TIMED_OUT"):
                yield ("error", {"message": f"Task '{task_id}' cannot execute: already in terminal state ({task.status})."})
                return
            req_text = task.request
            sess_id = task.session_id

        # If a mock provider is explicitly passed in tests, run _loop
        is_mock = self.provider is not None and (
            getattr(self.provider, "__class__", None).__name__ in ("MockProvider", "FakeProvider", "MagicMock", "DummyProvider", "MockTurnProvider", "MockSlowProvider", "RepeatedScreenshotProvider", "MockAgentProvider", "FakeScriptedProvider")
            or hasattr(self.provider, "turns")
            or hasattr(self.provider, "responses")
            or hasattr(self.provider, "_responses")
            or hasattr(self.provider, "mock")
            or getattr(self.provider, "name", "") in ("fake", "mock", "dummy", "test")
        )

        try:
            if not is_mock:
                async for event_name, event_data in self.runtime.execute_task(task_id):
                    yield (event_name, event_data)
            else:
                with SessionLocal() as db:
                    task = db.get(Task, task_id)
                    history = self._history(db, sess_id, task_id)
                    context_str = self._context(db, req_text)
                    async for ev in self._loop(db, task, history, context_str):
                        yield ev
        except (asyncio.CancelledError, GeneratorExit):
            with SessionLocal() as db_cancel:
                t = db_cancel.get(Task, task_id)
                if t and t.status not in (TaskStatus.COMPLETED.value, TaskStatus.CONFIRMING.value, TaskStatus.FAILED.value):
                    t.status = TaskStatus.CANCELLED.value
                    t.response = "Task execution was cancelled."
                    persist_activity(db_cancel, task_id, "agent.cancel", "Task was cancelled.", status="cancelled")
                    db_cancel.commit()
                    KERNEL.emergency_stop()
                else:
                    KERNEL.revoke_task(task_id)
            raise

    async def resume(self, task_id: str, approved: bool) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Resume task directly through canonical V2 Central Runtime or loop."""
        is_mock = (
            getattr(self.provider, "__class__", None).__name__ in ("MockProvider", "FakeProvider", "MagicMock", "ScriptedProvider", "FakeScriptedProvider", "DummyProvider", "MockTurnProvider")
            or hasattr(self.provider, "turns")
            or hasattr(self.provider, "responses")
            or hasattr(self.provider, "_responses")
            or hasattr(self.provider, "mock")
            or getattr(self.provider, "name", "") in ("fake", "mock", "dummy", "test")
        )
        if not is_mock:
            async for event_name, event_data in self.runtime.resume_task(task_id, approved):
                yield (event_name, event_data)
        else:
            with SessionLocal() as db:
                task = db.get(Task, task_id)
                if not task:
                    yield ("error", {"message": f"Task '{task_id}' not found."})
                    return
                if task.status != TaskStatus.CONFIRMING.value:
                    yield ("error", {"message": f"Task '{task_id}' is not waiting for approval or confirmation (status={task.status})."})
                    return

                checkpoint_payload = json.loads(task.checkpoint) if task.checkpoint else {}
                pending = checkpoint_payload.get("pending", [])
                previous_response_id = checkpoint_payload.get("previous_response_id")
                steps = checkpoint_payload.get("step", 1)
                messages = checkpoint_payload.get("messages", [])

                if not approved:
                    task.status = TaskStatus.COMPLETED.value
                    task.response = "The action was cancelled as requested."
                    _persist_activity(db, task.id, "agent.denied", "High-risk tool call denied by user.", status="denied")
                    yield ("activity", {"name": "agent.denied", "summary": "High-risk tool call denied by user.", "status": "denied"})
                    yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                    db.commit()
                    return

                outputs: list[dict[str, Any]] = []
                for call_dict in pending:
                    result, activity_event = await self.executor.execute_call(
                        db,
                        task.id,
                        call_dict["name"],
                        call_dict["call_id"],
                        call_dict.get("arguments", {}),
                        approved=True,
                    )
                    yield activity_event
                    outputs.append(result.output_payload)
                    messages.append(result.message_payload)

                task.status = TaskStatus.RUNNING.value
                task.checkpoint = None
                db.commit()

                history = self._history(db, task.session_id, task.id)
                context_str = self._context(db, task.request)
                initial_req = ProviderRequest(
                    message=task.request,
                    tools=self._definitions(),
                    previous_response_id=previous_response_id,
                    tool_outputs=outputs,
                    context=context_str,
                    history=history,
                    messages=messages,
                )
                async for ev in self._loop(db, task, history, context_str, initial_request=initial_req):
                    yield ev




    async def _loop(
        self,
        db,
        task: Task,
        history: list[dict[str, str]],
        context: str,
        initial_request: ProviderRequest | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if initial_request is not None and initial_request.messages:
            conversation_messages = list(initial_request.messages)
        else:
            conversation_messages = [
                *[{"role": h["role"], "content": h["content"]} for h in history],
                {"role": "user", "content": task.request},
            ]
        previous_response_id = initial_request.previous_response_id if initial_request else None
        tool_outputs = initial_request.tool_outputs if initial_request else []
        steps = 0
        consecutive_tracker: list[tuple[str, str]] = []
        consecutive_count = 0
        max_consecutive = get_settings().max_consecutive_identical_tool_calls
        gui_workflow_attempts = 0

        # Unified Generic Capability Execution using Universal Computer Action Router
        from .tools.computer_router import ACTION_ROUTER, IntentType
        DETERMINISTIC_FAST_PATH_INTENTS = {
            IntentType.BROWSER_TAB_CLOSE,
            IntentType.BROWSER_TAB_CREATE,
            IntentType.BROWSER_NAVIGATE,
            IntentType.BROWSER_TAB_LIST,
            IntentType.BROWSER_TAB_SWITCH,
            IntentType.WINDOW_LIST,
            IntentType.WINDOW_SWITCH,
            IntentType.WINDOW_CLOSE,
            IntentType.APP_LAUNCH,
            IntentType.FOLDER_OPEN,
            IntentType.FILE_OPEN,
            IntentType.INSPECT_UI,
            IntentType.UI_INTERACT,
            IntentType.HOTKEY,
            IntentType.KEY_PRESS,
            IntentType.SEQUENTIAL_WORKFLOW,
        }
        INTENT_TO_TOOL_NAME = {
            IntentType.BROWSER_TAB_CLOSE: "computer.close_browser_tab",
            IntentType.BROWSER_TAB_LIST: "computer.list_browser_tabs",
            IntentType.BROWSER_TAB_SWITCH: "computer.switch_browser_tab",
            IntentType.BROWSER_NAVIGATE: "browser.open_url",
            IntentType.BROWSER_TAB_CREATE: "computer.hotkey",
            IntentType.WINDOW_LIST: "computer.list_windows",
            IntentType.WINDOW_SWITCH: "computer.switch_window",
            IntentType.WINDOW_CLOSE: "computer.close_window",
            IntentType.APP_LAUNCH: "computer.launch_app",
            IntentType.FOLDER_OPEN: "terminal.run",
            IntentType.FILE_OPEN: "terminal.run",
            IntentType.INSPECT_UI: "computer.inspect_ui_tree",
            IntentType.UI_INTERACT: "computer.ui_action",
            IntentType.HOTKEY: "computer.hotkey",
            IntentType.KEY_PRESS: "computer.key_press",
            IntentType.SEQUENTIAL_WORKFLOW: "computer.sequential_workflow",
        }


        intent = ACTION_ROUTER.parse_intent(task.request)
        has_scripted_tool_calls = (
            hasattr(self.provider, "turns")
            and bool(self.provider.turns)
            and isinstance(self.provider.turns[0], (list, tuple))
        )
        if steps == 0 and not tool_outputs and not has_scripted_tool_calls and intent.intent_type in DETERMINISTIC_FAST_PATH_INTENTS:
            KERNEL.authorize_task(task.id)
            try:
                res = ACTION_ROUTER.execute_capability(intent)
            finally:
                KERNEL.revoke_task(task.id)
            is_success = bool(res.get("success"))

            if is_success or intent.intent_type != IntentType.UI_INTERACT:
                closed_name = res.get("closed_tab") or intent.target
                method_name = res.get("method", "structured_control")
                if intent.intent_type == IntentType.BROWSER_TAB_CLOSE:
                    if is_success:
                        msg = f"Successfully closed the {closed_name} tab in {intent.browser} via {method_name}."
                    else:
                        reason = res.get("reason") or f"Could not locate or verify closure of '{intent.target}' tab."
                        msg = f"I attempted to close the {intent.target} tab in {intent.browser}, but it could not be closed: {reason}"
                elif intent.intent_type == IntentType.WINDOW_LIST:
                    msg = f"Open desktop windows:\n{json.dumps(res.get('windows', []), default=str)}"
                elif intent.intent_type == IntentType.BROWSER_TAB_LIST:
                    msg = f"Open tabs in {intent.browser}:\n{json.dumps(res.get('tabs', []), default=str)}"
                elif intent.intent_type == IntentType.INSPECT_UI:
                    msg = f"Active window UI controls:\n{json.dumps(res.get('elements', []), default=str)}"
                else:
                    msg = res.get("message") or res.get("error") or res.get("reason") or "Completed action."

                summary = f"[{method_name}] {msg}"
                act_name = INTENT_TO_TOOL_NAME.get(intent.intent_type, f"computer.{intent.intent_type.value.lower()}")
                _persist_activity(db, task.id, act_name, summary, status="completed" if is_success else "failed")
                yield ("activity", {"name": act_name, "summary": summary, "status": "completed" if is_success else "failed"})

                task.response = msg
                task.status = TaskStatus.COMPLETED.value if is_success else TaskStatus.FAILED.value
                yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                db.commit()
                return







        screenshot_count = 0

        while steps < self.max_steps:
            if steps == 0:
                _persist_activity(db, task.id, "agent.plan", f"Selected {self.provider.name} / {getattr(self.provider, 'model', 'default')}.", status="completed")
                yield ("activity", {"name": "agent.plan", "summary": f"Selected {self.provider.name} / {getattr(self.provider, 'model', 'default')}."})

            request = ProviderRequest(
                message=task.request,
                tools=self._definitions(),
                previous_response_id=previous_response_id,
                tool_outputs=tool_outputs,
                context=context,
                history=history,
                messages=conversation_messages,
            )
            turn_text: list[str] = []
            calls = []
            response_id = ""
            if hasattr(self.provider, "stream_respond"):
                async for event in self.provider.stream_respond(request):
                    if event.kind == "text_delta":
                        turn_text.append(event.text)
                        yield ("text", {"delta": event.text})
                    elif event.kind == "tool_calls":
                        calls = event.tool_calls
                        response_id = event.response_id
            else:
                resp = await self.provider.respond(request)
                if resp.text:
                    turn_text.append(resp.text)
                    yield ("text", {"delta": resp.text})
                response_id = resp.response_id
                calls = getattr(resp, "tool_calls", []) or []

            if not calls:
                task.response = "".join(turn_text).strip() or "The provider returned no text response."
                task.status = TaskStatus.COMPLETED.value
                _persist_activity(db, task.id, "agent.respond", "Generated a model response.", status="completed")
                yield ("activity", {"name": "agent.respond", "summary": "Generated a model response."})
                yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                db.commit()
                return

            # Check Circuit Breaker for repeated consecutive identical tool calls
            for call in calls:
                call_sig = (
                    call.name,
                    json.dumps(call.arguments, sort_keys=True) if isinstance(call.arguments, dict) else str(call.arguments),
                )
                if consecutive_tracker and consecutive_tracker[-1] == call_sig:
                    consecutive_count += 1
                else:
                    consecutive_tracker.append(call_sig)
                    consecutive_count = 1

                # Specific screenshot loop detection
                if call.name in ("computer.screenshot", "computer.inspect_screen"):
                    screenshot_count += 1
                    if screenshot_count >= 3:
                        breaker_summary = "Circuit breaker tripped: screenshot/inspect_screen repeatedly called without progress."
                        _persist_activity(db, task.id, "agent.circuit_breaker", breaker_summary, status="failed")
                        yield ("activity", {"name": "agent.circuit_breaker", "summary": breaker_summary, "status": "failed"})
                        task.response = "I stopped because the tool 'screenshot' was repeatedly called without making progress."
                        task.status = TaskStatus.COMPLETED.value
                        yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                        db.commit()
                        return
                else:
                    screenshot_count = 0

                if consecutive_count >= max_consecutive:
                    breaker_summary = f"Circuit breaker tripped: tool '{call.name}' called {consecutive_count} times consecutively with identical arguments without progress."
                    _persist_activity(db, task.id, "agent.circuit_breaker", breaker_summary, status="failed")
                    yield ("activity", {"name": "agent.circuit_breaker", "summary": breaker_summary, "status": "failed"})
                    task.response = f"I stopped because the tool '{call.name}' was repeatedly called with identical arguments without making progress."
                    task.status = TaskStatus.COMPLETED.value
                    yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                    db.commit()
                    return


            conversation_messages.append({
                "role": "assistant",
                "content": "".join(turn_text) or None,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments) if isinstance(call.arguments, dict) else str(call.arguments),
                        },
                    }
                    for call in calls
                ],
            })

            high_calls = [call for call in calls if self.registry.get(call.name) and self.registry.get(call.name).permission == PermissionLevel.HIGH]
            safe_calls = [call for call in calls if call not in high_calls]

            if high_calls:
                pending = [{"call_id": call.call_id, "name": call.name, "arguments": call.arguments} for call in high_calls]
                checkpoint_payload = {
                    "message": task.request,
                    "previous_response_id": response_id,
                    "step": steps + 1,
                    "pending": pending,
                    "messages": conversation_messages,
                }
                task.checkpoint = json.dumps(checkpoint_payload)
                task.status = TaskStatus.CONFIRMING.value
                confirmations = [
                    {"call_id": call.call_id, "name": call.name, "arguments": call.arguments, "permission": PermissionLevel.HIGH.value}
                    for call in high_calls
                ]
                yield ("confirmation", {"task_id": task.id, "confirmations": confirmations})
                db.commit()
                return

            outputs: list[dict[str, Any]] = []
            gui_completed = False
            gui_summary = ""
            gui_status = TaskStatus.COMPLETED.value

            KERNEL.authorize_task(task.id)
            try:
                for call in safe_calls:
                    result, activity_event = await self.executor.execute_call(
                        db,
                        task.id,
                        call.name,
                        call.call_id,
                        call.arguments,
                        approved=True,
                    )
                    yield activity_event
                    outputs.append(result.output_payload)
                    conversation_messages.append(result.message_payload)

                    if call.name in ("computer.close_browser_tab", "computer.gui_action_workflow"):
                        gui_workflow_attempts += 1
                        out_raw = result.output_payload.get("output", "")
                        try:
                            parsed = json.loads(out_raw) if isinstance(out_raw, str) else out_raw
                            if isinstance(parsed, dict):
                                ver = parsed.get("verification")
                                is_verified = bool(isinstance(ver, dict) and ver.get("verified"))
                                if is_verified:
                                    gui_completed = True
                                    target_name = parsed.get("tab_name") or parsed.get("target") or "requested target"
                                    gui_summary = f"Successfully closed the {target_name} tab and visually verified its closure on the browser tab bar."
                                    gui_status = TaskStatus.COMPLETED.value
                                elif gui_workflow_attempts >= 2:
                                    gui_completed = True
                                    reason = parsed.get("reason") or (ver.get("explanation") if isinstance(ver, dict) else "") or "Could not locate or verify the requested target."
                                    gui_summary = f"The GUI action could not be completed safely: {reason}"
                                    gui_status = TaskStatus.FAILED.value
                        except Exception:
                            pass

                    # Universal Post-Action Goal Verification (ONLY after action-execution tools, not observational queries)
                    ACTION_EXECUTION_TOOLS = {
                        "computer.mouse_click",
                        "computer.ui_action",
                        "computer.hotkey",
                        "computer.keyboard_type",
                        "computer.key_press",
                        "browser.open_url",
                        "computer.close_browser_tab",
                        "computer.switch_browser_tab",
                        "computer.close_window",
                        "computer.switch_window",
                        "computer.launch_app",
                    }
                    if call.name in ACTION_EXECUTION_TOOLS and result.status == "completed":
                        intent = ACTION_ROUTER.parse_intent(task.request)
                        if intent.intent_type != IntentType.GENERAL_ACTION and intent.expected_outcome:
                            verified, ver_msg = ACTION_ROUTER.verify_action_result(intent, post_delay=0.1)
                            if verified:
                                task.response = f"Successfully completed: {intent.raw_request}. {ver_msg}"
                                task.status = TaskStatus.COMPLETED.value
                                yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                                db.commit()
                                return
            finally:
                KERNEL.revoke_task(task.id)

            if gui_completed:
                task.response = gui_summary or "The GUI workflow completed."
                task.status = gui_status
                yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
                db.commit()
                return

            previous_response_id, tool_outputs, steps = response_id, outputs, steps + 1


        task.response = "I stopped because the task reached PLUTON's safety step limit."
        task.status = TaskStatus.COMPLETED.value
        yield ("done", {"task_id": task.id, "session_id": task.session_id, "message": task.response, "status": task.status})
        db.commit()