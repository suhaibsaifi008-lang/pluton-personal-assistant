"""
PLUTON V2 — Universal Orchestration & Target/Context Master Regression Suite
Validates universal domain classification, search query extraction, canonical URL builder,
dynamic target binding, context lifecycle, and cross-application workflows.
"""

import os
import pytest
import urllib.parse
from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TargetDomain,
    VerificationStrategy,
    WorkflowContext,
)
from app.planning.intent_compiler import (
    UNIVERSAL_PLAN_COMPILER,
    SearchQueryExtractor,
    UniversalAppRegistry,
)
from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.kernel.control_kernel import KERNEL


def test_target_domain_classification_completeness():
    """Verify all 12 canonical target domains exist in TargetDomain enum."""
    expected = {
        "APP", "WINDOW", "BROWSER", "TAB", "WEBPAGE", "WEB_ELEMENT",
        "UI_ELEMENT", "FILE", "FOLDER", "PROCESS", "TERMINAL", "CLIPBOARD"
    }
    actual = {d.value for d in TargetDomain}
    assert expected.issubset(actual), f"Missing domains: {expected - actual}"


def test_universal_app_registry_normalization():
    """Verify application aliases normalize to canonical app identities without hardcoded hacks."""
    calc_res = UniversalAppRegistry.resolve("Calculator")
    assert calc_res is not None
    assert calc_res["canonical_name"] == "Calculator"
    assert calc_res["domain"] == TargetDomain.APP

    calc_alias = UniversalAppRegistry.resolve("calc")
    assert calc_alias is not None
    assert calc_alias["canonical_name"] == "Calculator"

    notepad_res = UniversalAppRegistry.resolve("notepad")
    assert notepad_res is not None
    assert notepad_res["canonical_name"] == "Notepad"

    explorer_res = UniversalAppRegistry.resolve("File Explorer")
    assert explorer_res is not None
    assert explorer_res["canonical_name"] == "File Explorer"

    downloads_res = UniversalAppRegistry.resolve("Downloads")
    assert downloads_res is not None
    assert downloads_res["domain"] == TargetDomain.FOLDER


def test_search_query_extraction():
    """Verify clean search query extraction without wrapper noise."""
    q1 = SearchQueryExtractor.extract_query("Search Google for YouTube")
    assert q1 == "YouTube"

    q2 = SearchQueryExtractor.extract_query("search for Gmail on Google")
    assert q2 == "Gmail"

    q3 = SearchQueryExtractor.extract_query("search YouTube in Brave")
    assert q3 == "YouTube"

    q4 = SearchQueryExtractor.extract_query("search 'Python documentation'")
    assert q4 == "Python documentation"


def test_search_query_extraction_multiple():
    """Verify search query extraction across various command structures."""
    assert SearchQueryExtractor.extract_query("Search Google for YouTube") == "YouTube"
    assert SearchQueryExtractor.extract_query("search for Pluton AI Control on Google") == "Pluton AI Control"


def test_task_state_isolation():
    """Verify separate tasks maintain strict context isolation without leaking mutable state."""
    ctx1 = ExecutionContext(task_id="task-iso-1")
    ctx2 = ExecutionContext(task_id="task-iso-2")
    
    ctx1.bound_hwnd = 12345
    assert ctx2.bound_hwnd != 12345
    assert ctx2.bound_hwnd is None


def test_plan_compilation_calculator():
    """Verify 'Open Calculator' compiles to APP domain launch, not general.action."""
    ctx = ExecutionContext(task_id="test-calc-plan")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open Calculator", ctx)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.action.capability == CapabilityType.APP_LAUNCH
    assert step.action.target == "calculator"
    assert step.target_domain == TargetDomain.APP


def test_plan_compilation_google_search():
    """Verify 'Open Google in Brave and search for YouTube' compiles cleanly."""
    query = "Open Google in Brave and search for YouTube."
    ctx = ExecutionContext(task_id="test-search-plan")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan(query, ctx)
    
    assert len(plan.steps) >= 2
    search_step = plan.steps[-1]
    assert search_step.action.capability == CapabilityType.WEB_TYPE
    assert search_step.action.parameters["text"] == "YouTube"
    assert search_step.action.target == "search box"


def test_plan_compilation_cross_app_notepad_explorer():
    """Verify multi-step cross-application workflow compiles into structured sequential plan."""
    query = "Open Notepad and File Explorer. Type PLUTON PHASE 1 into Notepad, save it as phase1.txt in Downloads, and verify the file exists."
    ctx = ExecutionContext(task_id="test-cross-app-plan")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan(query, ctx)
    
    caps = [s.action.capability for s in plan.steps]
    assert CapabilityType.APP_LAUNCH in caps
    assert CapabilityType.KEYBOARD_TYPE in caps
    assert CapabilityType.FILESYSTEM_WRITE in caps
    assert CapabilityType.FILESYSTEM_READ in caps

    # Verify save path in Downloads
    write_step = next(s for s in plan.steps if s.action.capability == CapabilityType.FILESYSTEM_WRITE)
    assert "phase1.txt" in write_step.action.target
    assert "Downloads" in write_step.action.target
