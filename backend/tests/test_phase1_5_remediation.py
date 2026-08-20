"""
PLUTON V2 — Phase 1.5 Remediation & Regression Test Suite
Validates all verified audit findings and security hardening:
1. Terminal command risk classification, destructive pattern blocking, and policy gating.
2. Filesystem canonical path boundaries, traversal blocking, and deep verification.
3. Target resolver HWND liveness verification via user32.IsWindow.
4. Kernel token preemption and explicit revocation consistency.
"""

import os
import sys
import time
from pathlib import Path
import pytest

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    VerificationStrategy,
)
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer import (
    COMPUTER_ENGINE,
    TARGET_RESOLVER,
    ComputerDomain,
    TargetResolutionStatus,
    TargetSpec,
)
from app.subsystems.computer.domains.terminal import CommandRiskLevel, TerminalSecurityPolicy
from app.subsystems.computer.domains.filesystem import FilesystemSecurityPolicy
from app.verification.verification_engine import VERIFICATION_ENGINE


# -----------------------------------------------------------------------------
# 1. TERMINAL SECURITY REGRESSION TESTS
# -----------------------------------------------------------------------------

def test_terminal_risk_classifier():
    """Verify that dangerous patterns are classified as CRITICAL/HIGH and benign as LOW/MEDIUM."""
    # Benign
    risk, _ = TerminalSecurityPolicy.classify_command("echo Hello Pluton")
    assert risk == CommandRiskLevel.LOW

    risk, _ = TerminalSecurityPolicy.classify_command("git status && pytest")
    assert risk == CommandRiskLevel.MEDIUM

    # Critical Destructive
    risk_fmt, _ = TerminalSecurityPolicy.classify_command("format C: /fs:NTFS")
    assert risk_fmt == CommandRiskLevel.CRITICAL

    risk_del, _ = TerminalSecurityPolicy.classify_command("del /f /s /q C:\\Windows\\System32")
    assert risk_del == CommandRiskLevel.CRITICAL

    risk_rmdir, _ = TerminalSecurityPolicy.classify_command("rmdir /s /q C:\\")
    assert risk_rmdir == CommandRiskLevel.CRITICAL

    risk_enc, _ = TerminalSecurityPolicy.classify_command("powershell.exe -encodedcommand dABlAHMAdAA=")
    assert risk_enc == CommandRiskLevel.CRITICAL

    risk_fork, _ = TerminalSecurityPolicy.classify_command(":(){ :|:& };:")
    assert risk_fork == CommandRiskLevel.CRITICAL

    # High Risk
    risk_kill, _ = TerminalSecurityPolicy.classify_command("taskkill /f /im *")
    assert risk_kill == CommandRiskLevel.HIGH


def test_terminal_blocks_critical_commands():
    """Verify that TerminalDomainHandler blocks critical commands unconditionally."""
    task_id = "test-terminal-sec-task"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)

    res = COMPUTER_ENGINE.terminal.execute("format D:", context=ctx)
    assert res["success"] is False
    assert "POLICY_DENIED" in res["error"]
    assert res["policy_status"] == "DENIED"

    res_del = COMPUTER_ENGINE.terminal.execute("del /f /s /q C:\\Windows", context=ctx)
    assert res_del["success"] is False
    assert "POLICY_DENIED" in res_del["error"]

    KERNEL.revoke_task(task_id)


def test_terminal_high_risk_requires_approval():
    """Verify that high-risk commands require explicit approval."""
    task_id = "test-terminal-high-task"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)

    # Without approval -> blocked
    res_unapproved = COMPUTER_ENGINE.terminal.execute("taskkill /f /im *", context=ctx, allow_high_risk=False)
    assert res_unapproved["success"] is False
    assert "REQUIRES_APPROVAL" in res_unapproved["error"]

    KERNEL.revoke_task(task_id)


# -----------------------------------------------------------------------------
# 2. FILESYSTEM SECURITY & PATH BOUNDARY TESTS
# -----------------------------------------------------------------------------

def test_filesystem_policy_path_boundaries(tmp_path):
    """Verify workspace path boundary enforcement and traversal blocking."""
    workspace = tmp_path / "sandbox"
    workspace.mkdir()
    policy = FilesystemSecurityPolicy(approved_roots=[workspace])

    # 1. Allowed path inside workspace
    valid_file = workspace / "allowed.txt"
    ok, resolved, err = policy.validate_path(str(valid_file))
    assert ok is True
    assert err is None

    # 2. Traversal attempt escaping workspace
    escape_file = workspace / ".." / "escaped.txt"
    ok, resolved, err = policy.validate_path(str(escape_file))
    assert ok is False
    assert "PATH_POLICY_DENIED" in err

    # 3. System absolute path attempt
    sys_file = r"C:\Windows\System32\cmd.exe"
    ok, resolved, err = policy.validate_path(sys_file)
    assert ok is False
    assert "PATH_POLICY_DENIED" in err


def test_filesystem_domain_blocks_outside_workspace_write(tmp_path):
    """Verify FilesystemDomainHandler rejects writing outside approved roots."""
    task_id = "test-fs-sec-task"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)

    # Attempt write to system path
    res = COMPUTER_ENGINE.filesystem.write(r"C:\Windows\System32\malicious_test.dll", "payload", context=ctx)
    assert res["success"] is False
    assert "PATH_POLICY_DENIED" in res["error"]

    KERNEL.revoke_task(task_id)


def test_filesystem_verification_content_and_size(tmp_path):
    """Verify enhanced FILESYSTEM_CHECK detects size and content mismatches."""
    test_file = tmp_path / "verify_test.txt"
    test_file.write_text("Hello World", encoding="utf-8")

    # Correct content and min size
    ver_ok = VERIFICATION_ENGINE.verify_action(
        strategy=VerificationStrategy.FILESYSTEM_CHECK,
        target=str(test_file),
        expected_state="present",
        metadata={"expected_min_bytes": 5, "expected_content": "Hello World"},
    )
    assert ver_ok.verified is True

    # Content mismatch detection
    ver_bad_content = VERIFICATION_ENGINE.verify_action(
        strategy=VerificationStrategy.FILESYSTEM_CHECK,
        target=str(test_file),
        expected_state="present",
        metadata={"expected_content": "Different Text"},
    )
    assert ver_bad_content.verified is False
    assert "Content mismatch" in ver_bad_content.observed_state.get("error", "")

    # Size mismatch detection
    ver_bad_size = VERIFICATION_ENGINE.verify_action(
        strategy=VerificationStrategy.FILESYSTEM_CHECK,
        target=str(test_file),
        expected_state="present",
        metadata={"expected_min_bytes": 500},
    )
    assert ver_bad_size.verified is False
    assert "Size mismatch" in ver_bad_size.observed_state.get("error", "")


# -----------------------------------------------------------------------------
# 3. TARGET RESOLVER HWND LIVENESS TESTS
# -----------------------------------------------------------------------------

def test_target_resolver_rejects_fake_hwnd():
    """Verify that TargetResolver rejects non-existent or stale HWNDs."""
    res = TARGET_RESOLVER.resolve(ComputerDomain.WINDOW, TargetSpec(hwnd=987654321))
    assert res.status in (TargetResolutionStatus.TARGET_NOT_FOUND, TargetResolutionStatus.STALE_TARGET)
    assert "not a valid or live window" in res.reason


# -----------------------------------------------------------------------------
# 4. KERNEL TOKEN PREEMPTION TESTS
# -----------------------------------------------------------------------------

def test_kernel_token_preemption_explicit_revocation():
    """Verify that when Task B preempts Task A, Token A is explicitly marked revoked."""
    task_a = "task-alpha"
    task_b = "task-beta"
    ctx_a = ExecutionContext(task_id=task_a)
    token_a = KERNEL.authorize_task(task_a, context=ctx_a)
    assert token_a.is_valid is True
    assert token_a.revoked is False

    # Preempt with Task B
    ctx_b = ExecutionContext(task_id=task_b)
    token_b = KERNEL.authorize_task(task_b, context=ctx_b)

    # Token A MUST be revoked
    assert token_a.revoked is True
    assert token_a.is_valid is False

    # Token B is valid
    assert token_b.is_valid is True
    assert token_b.revoked is False

    # Task A cannot execute
    with pytest.raises(PermissionError):
        KERNEL.assert_authorized(task_a)

    # Task B can execute
    KERNEL.assert_authorized(task_b)

    KERNEL.revoke_task(task_b)
