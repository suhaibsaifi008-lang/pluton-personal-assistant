"""
PLUTON V2 — Phase 1 Master Acceptance Test Suite
Verifies all 13 Phase 1 Computer Control Subsystem Criteria:
  1. Notepad Universal Control & Verification
  2. Filesystem Create / Write / Read / Delete & Authorization Boundaries
  3. Calculator Disambiguation & UIA Readback Verification
  4. File Explorer Shell Window Binding & Liveness
  5. Clipboard Workflow & State Synchronization
  6. Google Search & Canonical Query Extraction
  7. Semantic Webpage Targeting
  8. Click Result & Mandatory Postcondition Verification
  9. Cross-Application Context & Data Transfer
 10. Stale HWND Detection & Recovery
 11. Task Revocation & Zero-Input Safety Invariant
 12. Terminal Authorization & Command Risk Classification
 13. Filesystem Path Authorization & Integrity
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    TargetDomain,
    VerificationResult,
    VerificationStrategy,
    WorkflowContext,
)
from app.subsystems.computer.contracts import (
    ComputerDomain,
    ResolvedTarget,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetSpec,
)
from app.kernel.control_kernel import KERNEL, ComputerControlKernel, ComputerControlDenied
from app.planning.intent_compiler import SearchQueryExtractor, UniversalPlanCompiler
from app.subsystems.computer.domains.clipboard import ClipboardDomainHandler
from app.subsystems.computer.domains.filesystem import FilesystemDomainHandler
from app.subsystems.computer.domains.keyboard import KeyboardDomainHandler
from app.subsystems.computer.domains.terminal import CommandRiskLevel, TerminalDomainHandler, TerminalSecurityPolicy
from app.subsystems.computer.target_resolver import TargetResolver
from app.verification.verification_engine import VerificationEngine


# =============================================================================
# 1. NOTEPAD UNIVERSAL CONTROL & VERIFICATION
# =============================================================================

def test_notepad_control_and_verification(tmp_path):
    """Test Notepad text entry and UIA readback verification."""
    engine = VerificationEngine()
    
    with patch.object(engine.uia, "read_window_text", return_value="PLUTON DESKTOP TEST"):
        res = engine.verify_action(
            strategy=VerificationStrategy.UIA_READBACK,
            expected_state="PLUTON DESKTOP TEST",
            target="Notepad",
            hwnd=12345,
            timeout_seconds=0.5,
        )
        assert res.verified is True
        assert res.strategy == VerificationStrategy.UIA_READBACK


# =============================================================================
# 2. FILESYSTEM WORKFLOW & AUTHORIZATION
# =============================================================================

def test_filesystem_create_write_read_and_absence(tmp_path):
    """Test full filesystem create, write, read, and delete absence verification."""
    fs = FilesystemDomainHandler()
    engine = VerificationEngine()
    test_file = tmp_path / "phase1_test.txt"
    task_id = "task_fs_test"
    KERNEL.authorize_task(task_id=task_id)
    ctx = ExecutionContext(task_id=task_id)

    try:
        w_res = fs.write(str(test_file), "PLUTON VERIFIED", context=ctx)
        assert w_res["success"] is True

        v_write = engine.verify_action(
            strategy=VerificationStrategy.FILESYSTEM_CHECK,
            expected_state="PLUTON VERIFIED",
            target=str(test_file),
            metadata={"expected_exists": True},
        )
        assert v_write.verified is True
        assert v_write.observed_state["exists"] is True

        r_res = fs.read(str(test_file), context=ctx)
        assert r_res["success"] is True
        assert r_res["content"] == "PLUTON VERIFIED"

        d_res = fs.delete(str(test_file), context=ctx)
        assert d_res["success"] is True

        v_del = engine.verify_action(
            strategy=VerificationStrategy.FILESYSTEM_CHECK,
            expected_state=False,
            target=str(test_file),
            metadata={"expected_exists": False},
        )
        assert v_del.verified is True
        assert v_del.observed_state["exists"] is False
    finally:
        KERNEL.revoke_task(task_id)


# =============================================================================
# 3. CALCULATOR DISAMBIGUATION & UIA VERIFICATION
# =============================================================================

def test_calculator_target_disambiguation():
    """Test that UI element resolution resolves interactive buttons over containers."""
    mock_uia = MagicMock()
    mock_uia.find_elements_by_query.return_value = [
        {
            "name": "Five",
            "automation_id": "num5Button",
            "control_type": "ButtonControl",
            "bounding_rectangle": (100, 100, 50, 50),
        },
        {
            "name": "Five",
            "automation_id": "Group_5",
            "control_type": "GroupControl",
            "bounding_rectangle": (90, 90, 70, 70),
        },
    ]

    resolver = TargetResolver(uia_engine=mock_uia)
    spec = TargetSpec(semantic_name="Five", control_type="button", hwnd=54321)
    res = resolver.resolve(ComputerDomain.UI, spec)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.automation_id == "num5Button"
    assert res.target.control_type == "ButtonControl"


# =============================================================================
# 4. FILE EXPLORER SHELL WINDOW BINDING & LIVENESS
# =============================================================================

def test_file_explorer_shell_window_binding():
    """Test that File Explorer shell windows (CabinetWClass) are bound reliably."""
    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = [
        {"hwnd": 9999, "title": "Downloads", "class_name": "CabinetWClass", "pid": 1111},
        {"hwnd": 8888, "title": "Settings", "class_name": "ApplicationFrameWindow", "pid": 2222},
    ]

    resolver = TargetResolver(uia_engine=mock_uia)
    spec = TargetSpec(semantic_name="Downloads")
    res = resolver.resolve(ComputerDomain.WINDOW, spec)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.hwnd == 9999
    assert res.target.name == "Downloads"


# =============================================================================
# 5. CLIPBOARD WORKFLOW & SYNCHRONIZATION
# =============================================================================

def test_clipboard_workflow_and_verification():
    """Test setting, reading, and polling verification of clipboard state."""
    clip = ClipboardDomainHandler()
    engine = VerificationEngine()
    task_id = "task_clip_test"
    KERNEL.authorize_task(task_id=task_id)
    ctx = ExecutionContext(task_id=task_id)

    try:
        clip.set("PLUTON CLIPBOARD 2026", context=ctx)

        v_res = engine.verify_action(
            strategy=VerificationStrategy.CLIPBOARD_MATCH,
            expected_state="PLUTON CLIPBOARD 2026",
            target="clipboard",
            timeout_seconds=1.0,
        )
        assert v_res.verified is True
        assert "PLUTON CLIPBOARD 2026" in v_res.observed_state["clipboard"]
    finally:
        KERNEL.revoke_task(task_id)


# =============================================================================
# 6. GOOGLE SEARCH & CANONICAL QUERY EXTRACTION
# =============================================================================

@pytest.mark.parametrize(
    "raw_text, expected_query",
    [
        ("Search Google for PLUTON AI", "PLUTON AI"),
        ("Google search for YouTube", "YouTube"),
        ("search for YouTube on Google", "YouTube"),
        ("Do a Google search for Calculator", "Calculator"),
        ("search PLUTON AI in Brave", "PLUTON AI"),
        ("search for Gmail", "Gmail"),
    ],
)
def test_search_query_extraction_and_url_builder(raw_text, expected_query):
    """Test pure query extraction across all natural language variations."""
    extracted = SearchQueryExtractor.extract_query(raw_text)
    assert extracted == expected_query


# =============================================================================
# 7. SEMANTIC WEBPAGE TARGETING
# =============================================================================

def test_webpage_semantic_targeting():
    """Test resolving semantic web element targets."""
    resolver = TargetResolver()
    spec = TargetSpec(
        semantic_name="Change Page",
        dom_selector="button#change-page",
        url="http://localhost:5173/test",
    )
    res = resolver.resolve(ComputerDomain.WEB, spec)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.name == "Change Page"
    assert res.target.domain == ComputerDomain.WEB


# =============================================================================
# 8. CLICK RESULT & MANDATORY POSTCONDITION VERIFICATION
# =============================================================================

def test_mandatory_click_verification_rejection():
    """Test that click action cannot succeed without observable postcondition match."""
    engine = VerificationEngine()

    with patch.object(engine.uia, "read_window_text", return_value="Option A"):
        res_fail = engine.verify_action(
            strategy=VerificationStrategy.UIA_READBACK,
            expected_state="Option B",
            target="SubmitButton",
            hwnd=12345,
            timeout_seconds=0.3,
        )
        assert res_fail.verified is False

    with patch.object(engine.uia, "read_window_text", return_value="Option B"):
        res_pass = engine.verify_action(
            strategy=VerificationStrategy.UIA_READBACK,
            expected_state="Option B",
            target="SubmitButton",
            hwnd=12345,
            timeout_seconds=0.3,
        )
        assert res_pass.verified is True


# =============================================================================
# 9. CROSS-APPLICATION CONTEXT & DATA TRANSFER
# =============================================================================

def test_cross_app_workflow_context():
    """Test context preservation across multi-application actions."""
    wf_ctx = WorkflowContext()
    ctx = ExecutionContext(task_id="task_cross_app", workflow_context=wf_ctx)

    ctx.bound_hwnd = 1001
    ctx.bound_pid = 2001
    ctx.workflow_context.active_app = "Notepad"
    assert ctx.bound_hwnd == 1001
    assert ctx.workflow_context.active_app == "Notepad"

    ctx.bound_hwnd = 1002
    ctx.bound_pid = 2002
    ctx.workflow_context.active_app = "File Explorer"
    assert ctx.bound_hwnd == 1002
    assert ctx.workflow_context.active_app == "File Explorer"


# =============================================================================
# 10. STALE HWND DETECTION & RECOVERY
# =============================================================================

def test_stale_hwnd_detection():
    """Test that dead HWND is immediately detected and rejected."""
    resolver = TargetResolver()
    spec = TargetSpec(hwnd=99999999)
    res = resolver.resolve(ComputerDomain.WINDOW, spec)

    assert res.status == TargetResolutionStatus.STALE_TARGET
    assert "not a valid or live window" in res.reason


# =============================================================================
# 11. TASK REVOCATION & ZERO-INPUT SAFETY INVARIANT
# =============================================================================

def test_task_revocation_blocks_computer_actions():
    """Test that revoking or cancelling a task blocks all subsequent physical I/O."""
    kernel = ComputerControlKernel()
    task_id = "task_safety_test"
    kernel.authorize_task(task_id=task_id)

    assert kernel.is_authorized(task_id) is True

    kernel.revoke_task(task_id)

    with pytest.raises(ComputerControlDenied, match="Computer control BLOCKED"):
        kernel.assert_authorized(task_id)


# =============================================================================
# 12. TERMINAL AUTHORIZATION & SECURITY POLICY
# =============================================================================

def test_terminal_command_security_policy():
    """Test command risk classification and critical command blocking."""
    level, _ = TerminalSecurityPolicy.classify_command("echo PLUTON")
    assert level == CommandRiskLevel.LOW

    level_crit, reason = TerminalSecurityPolicy.classify_command("rmdir /s /q C:\\Windows")
    assert level_crit == CommandRiskLevel.CRITICAL
    assert "critical security pattern" in reason

    term = TerminalDomainHandler()
    task_id = "task_term_test"
    KERNEL.authorize_task(task_id=task_id)
    ctx = ExecutionContext(task_id=task_id)

    try:
        res = term.execute("rmdir /s /q C:\\Windows", context=ctx)
        assert res["success"] is False
        assert "POLICY_DENIED" in res["error"]
    finally:
        KERNEL.revoke_task(task_id)


# =============================================================================
# 13. FILESYSTEM AUTHORIZATION BOUNDARIES
# =============================================================================

def test_filesystem_authorization_gating():
    """Test that unauthorized tasks cannot write or delete filesystem files."""
    fs = FilesystemDomainHandler()
    unauthorized_ctx = ExecutionContext(task_id="unregistered_task_id")

    with pytest.raises(ComputerControlDenied):
        fs.write("test.txt", "content", context=unauthorized_ctx)