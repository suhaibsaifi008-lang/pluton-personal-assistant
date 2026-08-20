"""
PLUTON V2 — Unseen Target Acceptance Suite
Validates dynamic universality:
  1. Arbitrary / Unseen Web Domain Resolution (no hardcoded site lists)
  2. Dynamic Windows App Discovery (via Registry App Paths, PATH, Start Menu)
  3. Clean APP_NOT_FOUND (not AMBIGUOUS_TARGET) for nonexistent apps
  4. Multi-word Search vs Direct Navigation disambiguation
  5. Cross-Task Context Isolation (Zero Parameter Contamination)
  6. Universal Target Domain Classification
  7. Arbitrary File & Terminal Execution Verification
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
from app.kernel.control_kernel import KERNEL, ComputerControlKernel, ComputerControlDenied
from app.planning.intent_compiler import (
    SearchQueryExtractor,
    UniversalAppRegistry,
    UniversalPlanCompiler,
    UniversalWebNormalizer,
)
from app.subsystems.computer.contracts import (
    ComputerDomain,
    ResolvedTarget,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetSpec,
)
from app.subsystems.computer.domains.app import AppDomainHandler
from app.subsystems.computer.domains.filesystem import FilesystemDomainHandler
from app.subsystems.computer.domains.terminal import TerminalDomainHandler
from app.subsystems.computer.target_resolver import TargetResolver
from app.verification.verification_engine import VerificationEngine


# =============================================================================
# 1. ARBITRARY / UNSEEN WEB DOMAIN RESOLUTION
# =============================================================================

@pytest.mark.parametrize(
    "query, expected_url, expected_label",
    [
        ("anker.com", "https://anker.com", "anker.com"),
        ("hentaihaven.xxx", "https://hentaihaven.xxx", "hentaihaven.xxx"),
        ("example.org", "https://example.org", "example.org"),
        ("https://random-docs-123.ai/docs", "https://random-docs-123.ai/docs", "random-docs-123.ai"),
        ("arbitrarycompany.co.uk", "https://arbitrarycompany.co.uk", "arbitrarycompany.co.uk"),
        ("newstartupsite.io", "https://newstartupsite.io", "newstartupsite.io"),
        ("localhost:5173", "http://localhost:5173", "localhost:5173"),
    ],
)
def test_universal_web_normalizer_unseen_domains(query, expected_url, expected_label):
    """Test that arbitrary unseen web domains normalize correctly without finite registries."""
    res = UniversalWebNormalizer.normalize(query)
    assert res is not None
    url, label = res
    assert url == expected_url
    assert label == expected_label


def test_intent_compiler_navigates_unseen_website():
    """Test that intent compiler resolves 'open anker.com' to browser.navigate."""
    compiler = UniversalPlanCompiler()
    ctx = ExecutionContext(task_id="task_nav_unseen")
    
    plan = compiler.compile("open anker.com in Brave", ctx)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.action.capability == CapabilityType.BROWSER_NAVIGATE
    assert step.action.parameters["url"] == "https://anker.com"
    assert step.action.target_domain == TargetDomain.WEBPAGE


# =============================================================================
# 2. DYNAMIC WINDOWS APPLICATION DISCOVERY
# =============================================================================

def test_dynamic_app_discovery_resolves_system_apps():
    """Test dynamic discovery finds installed apps via PATH, Registry App Paths, or Start Menu."""
    # Test built-in/PATH apps
    calc = UniversalAppRegistry.resolve("calc")
    assert calc is not None
    assert "calc" in calc["exe"].lower()

    notepad = UniversalAppRegistry.resolve("notepad")
    assert notepad is not None
    assert "notepad" in notepad["exe"].lower()

    # Test powershell via PATH
    ps = UniversalAppRegistry.resolve("powershell")
    assert ps is not None
    assert "powershell" in ps["exe"].lower()


def test_dynamic_app_discovery_nonexistent_returns_none():
    """Test that non-existent applications return None, preventing AMBIGUOUS_TARGET."""
    res = UniversalAppRegistry.resolve("completely_made_up_app_xyz_999")
    assert res is None


def test_intent_compiler_plans_unseen_app():
    """Test intent compiler plans app.launch for any requested application."""
    compiler = UniversalPlanCompiler()
    ctx = ExecutionContext(task_id="task_app_unseen")
    
    plan = compiler.compile("Open Paint", ctx)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.action.capability == CapabilityType.APP_LAUNCH
    assert step.target_domain == TargetDomain.APP


# =============================================================================
# 3. MULTI-WORD SEARCH VS DIRECT NAVIGATION
# =============================================================================

def test_multi_word_unseen_web_search():
    """Test that natural multi-word web searches become canonical search type actions."""
    compiler = UniversalPlanCompiler()
    ctx = ExecutionContext(task_id="task_search_unseen")
    
    plan = compiler.compile("search for anker games in Brave", ctx)
    assert len(plan.steps) == 3
    assert plan.steps[1].action.capability == CapabilityType.WEB_TYPE
    assert plan.steps[1].action.parameters["text"] == "anker games"
    assert plan.steps[1].action.target == "search box"


# =============================================================================
# 4. CROSS-TASK ISOLATION (ZERO PARAMETER CONTAMINATION)
# =============================================================================

def test_cross_task_parameter_isolation():
    """Test that previous task parameters do NOT leak into subsequent distinct tasks."""
    compiler = UniversalPlanCompiler()

    # Task A: Search Gmail
    ctx_a = ExecutionContext(task_id="task_A")
    plan_a = compiler.compile("search Gmail", ctx_a)
    assert plan_a.steps[0].action.parameters["text"] == "Gmail"

    # Task B: Search Reddit (Must not have 'Gmail' in parameters)
    ctx_b = ExecutionContext(task_id="task_B")
    plan_b = compiler.compile("search Reddit", ctx_b)
    assert plan_b.steps[0].action.parameters["text"] == "Reddit"
    assert "Gmail" not in str(plan_b.steps[0].action.parameters)

    # Task C: Search Minecraft
    ctx_c = ExecutionContext(task_id="task_C")
    plan_c = compiler.compile("search Minecraft", ctx_c)
    assert plan_c.steps[0].action.parameters["text"] == "Minecraft"
    assert "Reddit" not in str(plan_c.steps[0].action.parameters)
    assert "Gmail" not in str(plan_c.steps[0].action.parameters)


# =============================================================================
# 5. ARBITRARY FILESYSTEM OPERATIONS & VERIFICATION
# =============================================================================

def test_arbitrary_unseen_filename_lifecycle(tmp_path):
    """Test creating, verifying, reading, and deleting a dynamically named arbitrary file."""
    fs = FilesystemDomainHandler()
    engine = VerificationEngine()
    
    unique_file = tmp_path / "unseen_dynamic_payload_7721.txt"
    payload_text = "DYNAMIC_UNIVERSAL_TEST_VERIFIED_2026"
    
    task_id = "task_dyn_fs"
    KERNEL.authorize_task(task_id=task_id)
    ctx = ExecutionContext(task_id=task_id)

    try:
        # Write
        w_res = fs.write(str(unique_file), payload_text, context=ctx)
        assert w_res["success"] is True

        # Verify existence
        v_write = engine.verify_action(
            strategy=VerificationStrategy.FILESYSTEM_CHECK,
            expected_state=payload_text,
            target=str(unique_file),
            metadata={"expected_exists": True},
        )
        assert v_write.verified is True

        # Read back
        r_res = fs.read(str(unique_file), context=ctx)
        assert r_res["success"] is True
        assert r_res["content"] == payload_text

        # Delete & verify absence
        fs.delete(str(unique_file), context=ctx)
        v_del = engine.verify_action(
            strategy=VerificationStrategy.FILESYSTEM_CHECK,
            expected_state=False,
            target=str(unique_file),
            metadata={"expected_exists": False},
        )
        assert v_del.verified is True
    finally:
        KERNEL.revoke_task(task_id)


# =============================================================================
# 6. ARBITRARY HARMLESS TERMINAL EXECUTION
# =============================================================================

def test_arbitrary_safe_terminal_command():
    """Test running an arbitrary safe terminal command and receiving structured exit code & stdout."""
    term = TerminalDomainHandler()
    task_id = "task_term_unseen"
    KERNEL.authorize_task(task_id=task_id)
    ctx = ExecutionContext(task_id=task_id)

    try:
        res = term.execute("powershell.exe -Command \"Write-Output 'PLUTON_UNIVERSAL_OK'\"", context=ctx)
        assert res["success"] is True
        assert res["exit_code"] == 0
        assert "PLUTON_UNIVERSAL_OK" in res["stdout"]
    finally:
        KERNEL.revoke_task(task_id)