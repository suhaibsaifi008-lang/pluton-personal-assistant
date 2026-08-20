"""
PLUTON V2 — Universal Computer Subsystem Unit & Integration Tests
Tests all 9 canonical domains, TargetResolver, ambiguity guards, and token gating.
"""

import pytest
from app.core.contracts import Action, CapabilityType, ExecutionContext, ExecutionTier
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer import (
    COMPUTER_ENGINE,
    TARGET_RESOLVER,
    ComputerDomain,
    TargetResolutionStatus,
    TargetSpec,
)


@pytest.fixture(autouse=True)
def auth_task():
    task_id = "test-phase1-task"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)
    yield ctx
    KERNEL.revoke_task(task_id)


def test_target_resolver_window_by_hwnd(auth_task):
    import ctypes
    real_hwnd = ctypes.windll.user32.GetDesktopWindow()
    res = TARGET_RESOLVER.resolve(
        ComputerDomain.WINDOW,
        TargetSpec(hwnd=real_hwnd),
    )
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.hwnd == real_hwnd



def test_target_resolver_ambiguous_target_guard(monkeypatch, auth_task):
    fake_windows = [
        {"title": "Document - WordPad", "hwnd": 1001, "pid": 501},
        {"title": "Document - WordPad", "hwnd": 1002, "pid": 502},
    ]
    monkeypatch.setattr(TARGET_RESOLVER.uia, "list_windows", lambda visible_only=True: fake_windows)

    res = TARGET_RESOLVER.resolve(
        ComputerDomain.WINDOW,
        TargetSpec(semantic_name="Document - WordPad"),
    )
    assert res.status == TargetResolutionStatus.AMBIGUOUS_TARGET
    assert len(res.candidates) == 2


def test_target_resolver_target_not_found(monkeypatch, auth_task):
    monkeypatch.setattr(TARGET_RESOLVER.uia, "list_windows", lambda visible_only=True: [])
    res = TARGET_RESOLVER.resolve(
        ComputerDomain.WINDOW,
        TargetSpec(semantic_name="NonExistentApp"),
    )
    assert res.status == TargetResolutionStatus.TARGET_NOT_FOUND


@pytest.mark.anyio
async def test_computer_engine_blocks_unauthorized_token():
    KERNEL.revoke_task("unauthed-task")
    ctx = ExecutionContext(task_id="unauthed-task")
    act = Action(
        capability=CapabilityType.KEYBOARD_TYPE,
        target="hello",
        parameters={"text": "hello"},
        tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
    )
    with pytest.raises(PermissionError):
        await COMPUTER_ENGINE.execute_action(act, ctx)


@pytest.mark.anyio
async def test_computer_engine_filesystem_domain(tmp_path, auth_task):
    test_file = tmp_path / "test_v2.txt"
    dest_file = tmp_path / "moved_v2.txt"

    # Write
    act_write = Action(
        capability=CapabilityType.FILESYSTEM_WRITE,
        target=str(test_file),
        parameters={"content": "Pluton V2 Subsystem"},
        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
    )
    res_write = await COMPUTER_ENGINE.execute_action(act_write, auth_task)
    assert res_write.status == "completed"
    assert test_file.read_text(encoding="utf-8") == "Pluton V2 Subsystem"

    # Read
    act_read = Action(
        capability=CapabilityType.FILESYSTEM_READ,
        target=str(test_file),
        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
    )
    res_read = await COMPUTER_ENGINE.execute_action(act_read, auth_task)
    assert res_read.status == "completed"
    assert res_read.observed["content"] == "Pluton V2 Subsystem"

    # Move via Domain
    move_res = COMPUTER_ENGINE.filesystem.move(str(test_file), str(dest_file), context=auth_task)
    assert move_res["success"] is True
    assert dest_file.exists()
    assert not test_file.exists()

    # Delete via Domain
    del_res = COMPUTER_ENGINE.filesystem.delete(str(dest_file), context=auth_task)
    assert del_res["success"] is True
    assert not dest_file.exists()


@pytest.mark.anyio
async def test_computer_engine_terminal_domain(auth_task):
    act = Action(
        capability=CapabilityType.TERMINAL_EXECUTE,
        target="echo PlutonTerminalOK",
        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
    )
    res = await COMPUTER_ENGINE.execute_action(act, auth_task)
    assert res.status == "completed"
    assert res.observed["exit_code"] == 0
    assert "PlutonTerminalOK" in res.observed["stdout"]
