"""
PLUTON V2 — Universal Intent & Multi-Domain Pipeline Verification Suite
Tests the 12-domain canonical computer-control substrate against the 8 real acceptance scenarios:
- TEST A: Open Notepad and type HELLO FROM PLUTON.
- TEST B: Open File Explorer and open Downloads.
- TEST C: Open Google in Brave, search YouTube.
- TEST D: Open Notepad, type TEST, copy it, create a new line, paste it.
- TEST E: Create a file called phase1.txt in Downloads and write Phase 1 into it.
- TEST F: Open Settings and switch to Bluetooth.
- TEST G: Open the local Pluton test webpage, type PLUTON TEST, enable the checkbox, select Option B, click the button, and report the result.
"""

import pytest
from app.core.contracts import CapabilityType, ExecutionContext, VerificationStrategy
from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER, TargetDomain


def test_universal_clause_splitting():
    """Verify natural language action boundaries are preserved without splitting quoted strings."""
    clauses = UNIVERSAL_PLAN_COMPILER.split_clauses(
        "Open Notepad. Type 'Hello, world', and then save it as test.txt."
    )
    assert len(clauses) >= 3
    assert any("Notepad" in c for c in clauses)
    assert any("Hello, world" in c for c in clauses)


def test_canonical_test_a_notepad_typing():
    """TEST A: Open Notepad and type HELLO FROM PLUTON."""
    ctx = ExecutionContext(task_id="test-a")
    plan = CAPABILITY_ROUTER.plan_request("Open Notepad and type HELLO FROM PLUTON.", ctx)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[0].action.target == "notepad"
    assert plan.steps[1].action.capability == CapabilityType.KEYBOARD_TYPE
    assert plan.steps[1].action.parameters["text"] == "HELLO FROM PLUTON"


def test_canonical_test_b_explorer_downloads():
    """TEST B: Open File Explorer and open Downloads."""
    ctx = ExecutionContext(task_id="test-b")
    plan = CAPABILITY_ROUTER.plan_request("Open File Explorer and open Downloads.", ctx)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[1].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[1].action.target == "downloads"


def test_canonical_test_c_search_youtube():
    """TEST C: Open Google in Brave, search YouTube."""
    ctx = ExecutionContext(task_id="test-c")
    plan = CAPABILITY_ROUTER.plan_request("Open Google in Brave, search YouTube.", ctx)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "google.com" in plan.steps[0].action.target
    assert plan.steps[1].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "youtube" in plan.steps[1].action.target.lower()


def test_canonical_test_d_notepad_copy_paste():
    """TEST D: Open Notepad, type TEST, copy it, create a new line, paste it."""
    ctx = ExecutionContext(task_id="test-d")
    plan = CAPABILITY_ROUTER.plan_request("Open Notepad, type TEST, copy it, create a new line, paste it.", ctx)
    assert len(plan.steps) == 5
    assert plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[1].action.capability == CapabilityType.KEYBOARD_TYPE
    assert plan.steps[2].action.capability == CapabilityType.KEYBOARD_COPY
    assert plan.steps[3].action.capability == CapabilityType.KEYBOARD_HOTKEY
    assert plan.steps[4].action.capability == CapabilityType.KEYBOARD_PASTE


def test_canonical_test_e_filesystem_create_file():
    """TEST E: Create a file called phase1.txt in Downloads and write Phase 1 into it."""
    ctx = ExecutionContext(task_id="test-e")
    plan = CAPABILITY_ROUTER.plan_request("Create a file called phase1.txt in Downloads and write Phase 1 into it.", ctx)
    assert len(plan.steps) == 1
    assert plan.steps[0].action.capability == CapabilityType.FILESYSTEM_WRITE
    assert "phase1.txt" in plan.steps[0].action.parameters["path"]
    assert plan.steps[0].action.parameters["content"] == "Phase 1"


def test_canonical_test_f_settings_bluetooth():
    """TEST F: Open Settings and switch to Bluetooth."""
    ctx = ExecutionContext(task_id="test-f")
    plan = CAPABILITY_ROUTER.plan_request("Open Settings and switch to Bluetooth.", ctx)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[1].action.capability == CapabilityType.APP_LAUNCH
    assert "bluetooth" in plan.steps[1].action.target


def test_canonical_test_g_web_interaction_full_pipeline():
    """TEST G: Open the local Pluton test webpage, type PLUTON TEST, enable the checkbox, select Option B, click the button, and report the result."""
    ctx = ExecutionContext(task_id="test-g")
    query = (
        "Open the Pluton Web Interaction Test Page in Brave. Enter PLUTON FRONTEND TEST in the text box, "
        "enable the checkbox, select Option B, click Change Page, and tell me the resulting text shown on the page."
    )
    plan = CAPABILITY_ROUTER.plan_request(query, ctx)
    assert len(plan.steps) == 6
    assert plan.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "test_page.html" in plan.steps[0].action.target
    assert plan.steps[1].action.capability == CapabilityType.WEB_TYPE
    assert plan.steps[1].action.parameters["text"] == "PLUTON FRONTEND TEST"
    assert plan.steps[2].action.capability == CapabilityType.WEB_CLICK
    assert plan.steps[3].action.capability == CapabilityType.WEB_SELECT
    assert plan.steps[3].action.parameters["value"] == "Option B"
    assert plan.steps[4].action.capability == CapabilityType.WEB_CLICK
    assert plan.steps[5].action.capability == CapabilityType.WEB_EXTRACT_TEXT
