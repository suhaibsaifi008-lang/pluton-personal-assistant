"""
Regression and hardening tests for Phase 1 Critical Bug Fixes:
1. Web resolver failure fix (no missing find_elements_by_query attribute).
2. Zero unexpected/random mouse clicks / right-clicks after action execution or task completion.
3. Strict target validation on coordinate mouse fallback.
4. Input rejection after task termination.
"""

import pytest
from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    TaskState,
)
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer import COMPUTER_ENGINE
from app.subsystems.computer.contracts import (
    ComputerDomain,
    TargetResolutionStatus,
    TargetSpec,
)
from app.subsystems.computer.target_resolver import TARGET_RESOLVER
from app.tools.uia_engine import UIA_ENGINE


def test_uia_engine_exposes_find_elements_by_query():
    """Verify UIA_ENGINE provides find_elements_by_query without crashing."""
    elems = UIA_ENGINE.find_elements_by_query("nonexistent_element_query_12345", max_results=5)
    assert isinstance(elems, list)


def test_ui_domain_handler_find_and_inspect():
    """Verify UI domain find does not raise AttributeError."""
    task_id = "test-ui-domain-find"
    context = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=context)
    try:
        res = COMPUTER_ENGINE.ui.find("nonexistent_ui_btn", hwnd=0, context=context)
        assert isinstance(res, list)
    finally:
        KERNEL.revoke_task(task_id)


def test_target_resolver_ui_element():
    """Verify TargetResolver._resolve_ui_element executes cleanly."""
    res = TARGET_RESOLVER.resolve(ComputerDomain.UI, TargetSpec(semantic_name="nonexistent_button"))
    assert res.status in (TargetResolutionStatus.TARGET_NOT_FOUND, TargetResolutionStatus.RESOLVED)


def test_web_domain_missing_element_returns_clean_error():
    """Verify web.find on missing element returns found=False instead of crashing."""
    import asyncio
    async def _run():
        task_id = "test-web-missing-elem"
        context = ExecutionContext(task_id=task_id)
        KERNEL.authorize_task(task_id, context=context)
        try:
            res = await COMPUTER_ENGINE.web.find("non_existent_element_xyz_999", context=context)
            assert res.get("found") is False or not res.get("success", True)
        finally:
            KERNEL.revoke_task(task_id)
    asyncio.run(_run())


def test_mouse_domain_rejects_none_coordinates():
    """Verify MouseDomainHandler.click rejects None coordinates."""
    task_id = "test-mouse-reject-none"
    context = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=context)
    try:
        res = COMPUTER_ENGINE.mouse.click(x=None, y=None, context=context)
        assert res["success"] is False
        assert "Explicit (x, y) screen coordinates required" in res["error"]
    finally:
        KERNEL.revoke_task(task_id)


def test_mouse_domain_rejects_out_of_bounds_coordinates():
    """Verify MouseDomainHandler.click rejects out-of-bounds coordinates."""
    task_id = "test-mouse-reject-oob"
    context = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=context)
    try:
        res = COMPUTER_ENGINE.mouse.click(x=999999, y=999999, context=context)
        assert res["success"] is False
        assert "out of physical screen bounds" in res["error"]
    finally:
        KERNEL.revoke_task(task_id)


def test_task_revocation_generates_zero_phantom_clicks(monkeypatch):
    """Verify KERNEL.revoke_task flushes inputs cleanly without sending phantom right-click events."""
    task_id = "test-clean-revocation"
    context = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=context)

    mouse_events_fired = []

    # Intercept user32.mouse_event if on Windows
    import ctypes
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        orig_mouse_event = ctypes.windll.user32.mouse_event
        def mock_mouse_event(flags, dx, dy, data, extra):
            mouse_events_fired.append(flags)
            return orig_mouse_event(flags, dx, dy, data, extra)
        monkeypatch.setattr(ctypes.windll.user32, "mouse_event", mock_mouse_event)

    # When no mouse buttons are physically down, revoke_task should NOT fire mouse_event
    KERNEL.revoke_task(task_id)

    # Assert 0 right-up or left-up events were fired because buttons were not held down
    assert len(mouse_events_fired) == 0


def test_zero_input_permitted_after_task_revocation():
    """Verify that after task is revoked, mouse and keyboard calls are rejected with PermissionError."""
    task_id = "test-post-revocation-blocked"
    context = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=context)
    KERNEL.revoke_task(task_id)

    with pytest.raises(PermissionError):
        COMPUTER_ENGINE.keyboard.type("Blocked text", context=context)

    with pytest.raises(PermissionError):
        COMPUTER_ENGINE.mouse.move(100, 100, context=context)
