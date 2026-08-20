"""
PLUTON V2 — Live Cutover Remediation & Regression Test Suite
Tests:
1. Model tool surface isolation (canonical capabilities visible, legacy tools excluded).
2. Natural language intent parsing for multi-word browser & application requests.
3. ToolExecutor sync & async coroutine execution contracts.
4. Browser domain routing & verification.
5. Structured runtime event streams and error handling.
"""

import asyncio
import json
import pytest

from app.capabilities.model_registry import CANONICAL_MODEL_REGISTRY
from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    VerificationStrategy,
)
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer import COMPUTER_ENGINE
from app.tool_executor import ToolExecutor
from app.tools.base import Tool, PermissionLevel, _schema


# -----------------------------------------------------------------------------
# 1. TOOL SURFACE ISOLATION TESTS
# -----------------------------------------------------------------------------

def test_canonical_tools_present_in_model_registry():
    """Verify that canonical V2 capabilities are present in the model registry."""
    tool_names = [t.name for t in CANONICAL_MODEL_REGISTRY.list()]

    # App Domain
    assert "app.launch" in tool_names
    assert "app.close" in tool_names

    # Window Domain
    assert "window.list" in tool_names
    assert "window.focus" in tool_names
    assert "window.close" in tool_names

    # Browser Domain
    assert "browser.list_tabs" in tool_names
    assert "browser.open_tab" in tool_names
    assert "browser.navigate" in tool_names
    assert "browser.switch_tab" in tool_names
    assert "browser.close_tab" in tool_names
    assert "browser.get_state" in tool_names

    # Keyboard & Mouse
    assert "keyboard.type" in tool_names
    assert "keyboard.press" in tool_names
    assert "keyboard.hotkey" in tool_names
    assert "mouse.click" in tool_names
    assert "mouse.move" in tool_names

    # Terminal & Filesystem
    assert "terminal.execute" in tool_names
    assert "filesystem.read" in tool_names
    assert "filesystem.write" in tool_names


def test_legacy_computer_tools_excluded_from_model_registry():
    """Verify that legacy competing/bypass tools are NOT exposed to the model."""
    tool_names = [t.name for t in CANONICAL_MODEL_REGISTRY.list()]

    assert "browser.open_url" not in tool_names
    assert "computer.list_browser_tabs" not in tool_names
    assert "computer.switch_browser_tab" not in tool_names
    assert "computer.close_browser_tab" not in tool_names
    assert "computer.mouse_click" not in tool_names
    assert "computer.keyboard_type" not in tool_names
    assert "computer.launch_app" not in tool_names


# -----------------------------------------------------------------------------
# 2. STRUCTURED INTENT PARSER TESTS
# -----------------------------------------------------------------------------

def test_intent_parsing_browser_destinations():
    """Verify natural conversational browser queries resolve to BROWSER_NAVIGATE."""
    ctx = ExecutionContext(task_id="test-intent-ctx")

    # "OPEN GMAIL IN MY BROWSER"
    plan_a = CAPABILITY_ROUTER.plan_request("OPEN GMAIL IN MY BROWSER", ctx)
    assert len(plan_a.steps) == 1
    assert plan_a.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "mail.google.com" in plan_a.steps[0].action.target

    # "OPEN GMAIL TAB IN MY BROWSER"
    plan_b = CAPABILITY_ROUTER.plan_request("OPEN GMAIL TAB IN MY BROWSER", ctx)
    assert len(plan_b.steps) == 1
    assert plan_b.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "mail.google.com" in plan_b.steps[0].action.target

    # "OPEN A NEW TAB AND OPEN GMAIL"
    plan_c = CAPABILITY_ROUTER.plan_request("OPEN A NEW TAB AND OPEN GMAIL", ctx)
    assert len(plan_c.steps) == 1
    assert plan_c.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "mail.google.com" in plan_c.steps[0].action.target

    # "OPEN GOOGLE IN MY BROWSER"
    plan_d = CAPABILITY_ROUTER.plan_request("OPEN GOOGLE IN MY BROWSER", ctx)
    assert len(plan_d.steps) == 1
    assert plan_d.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "google.com" in plan_d.steps[0].action.target


def test_intent_parsing_browser_tabs():
    """Verify browser tab listing and switching resolve to structured capabilities."""
    ctx = ExecutionContext(task_id="test-intent-ctx")

    # "LIST MY OPEN BROWSER TABS"
    plan_tabs = CAPABILITY_ROUTER.plan_request("LIST MY OPEN BROWSER TABS", ctx)
    assert len(plan_tabs.steps) == 1
    assert plan_tabs.steps[0].action.capability == CapabilityType.BROWSER_LIST_TABS

    # "SWITCH TO MY EXISTING GMAIL TAB"
    plan_switch = CAPABILITY_ROUTER.plan_request("SWITCH TO MY EXISTING GMAIL TAB", ctx)
    assert len(plan_switch.steps) == 1
    assert plan_switch.steps[0].action.capability == CapabilityType.BROWSER_SWITCH_TAB
    assert plan_switch.steps[0].action.target == "gmail"


def test_intent_parsing_notepad_workflow():
    """Verify single and compound desktop application workflows."""
    ctx = ExecutionContext(task_id="test-intent-ctx")

    # "OPEN NOTEPAD"
    plan_np = CAPABILITY_ROUTER.plan_request("OPEN NOTEPAD", ctx)
    assert len(plan_np.steps) == 1
    assert plan_np.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan_np.steps[0].action.target == "notepad"

    # "OPEN NOTEPAD AND TYPE HELLO FROM PLUTON"
    plan_compound = CAPABILITY_ROUTER.plan_request("OPEN NOTEPAD AND TYPE HELLO FROM PLUTON", ctx)
    assert len(plan_compound.steps) == 2
    assert plan_compound.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan_compound.steps[1].action.capability == CapabilityType.KEYBOARD_TYPE
    assert plan_compound.steps[1].action.target == "HELLO FROM PLUTON"


# -----------------------------------------------------------------------------
# 3. TOOL EXECUTOR ASYNC CONTRACT TESTS
# -----------------------------------------------------------------------------

def test_tool_executor_sync_and_async_tools(tmp_path):
    """Verify ToolExecutor cleanly executes both sync and async tools without serialization failures."""
    async def _test():
        from app.database import SessionLocal
        from app.kernel import KERNEL
        from app.core.contracts import ExecutionContext
        db = SessionLocal()
        task_id = "test-executor-task"
        ctx = ExecutionContext(task_id=task_id)
        KERNEL.authorize_task(task_id, context=ctx)
        executor = ToolExecutor(CANONICAL_MODEL_REGISTRY)

        # 1. Sync Tool: window.list
        res_sync, ev_sync = await executor.execute_call(
            db,
            task_id=task_id,
            name="window.list",
            call_id="call-sync-1",
            arguments={"visible_only": True},
        )
        assert res_sync.status == "completed", f"Sync failed: {res_sync.observed}"
        assert isinstance(res_sync.observed, dict)
        # Ensure JSON serializable
        assert json.dumps(res_sync.output_payload) is not None

        # 2. Async Tool Simulation
        async def sample_async_fn(val: str) -> dict[str, Any]:
            await asyncio.sleep(0.01)
            return {"received": val, "async_success": True}

        test_reg = CANONICAL_MODEL_REGISTRY
        test_reg.register(
            Tool("test.async_tool", "Async test tool", PermissionLevel.LOW, _schema({"val": {"type": "string"}}, ["val"]), sample_async_fn)
        )

        res_async, ev_async = await executor.execute_call(
            db,
            task_id="test-executor-task",
            name="test.async_tool",
            call_id="call-async-1",
            arguments={"val": "hello-async"},
        )
        assert res_async.status == "completed"
        assert res_async.observed.get("async_success") is True
        assert json.dumps(res_async.output_payload) is not None

        db.close()

    asyncio.run(_test())

