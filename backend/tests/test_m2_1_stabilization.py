"""
PLUTON V2 — M2.1 Stabilization & Browser Interaction Test Suite
Verifies:
1. VerificationStrategy compatibility and enum integrity.
2. Conversational routing across diverse knowledge/chat requests (zero computer execution).
3. File Explorer physical launch and verification on Windows 10/11.
4. Generic browser interaction pipeline (inspect, find, click, type, submit, 404 handling).
5. Task cancellation lifecycle and event contracts.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    IntentDomain,
    Plan,
    PlanStep,
    RiskLevel,
    TargetDomain,
    TaskState,
    VerificationResult,
    VerificationStrategy,
)
from app.router import FRONT_DOOR_ROUTER, RouteContext
from app.planning.intent_compiler import UniversalAppRegistry, UniversalWebNormalizer
from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.verification.verification_engine import VerificationEngine


# =============================================================================
# 1. VerificationStrategy Compatibility Tests
# =============================================================================

def test_verification_strategy_canonical_members():
    """Verify that canonical enum members exist and no stale members break contracts."""
    assert VerificationStrategy.NONE == "none"
    assert VerificationStrategy.UIA_READBACK == "uia_readback"
    assert VerificationStrategy.WINDOW_PRESENCE == "window_presence"
    assert VerificationStrategy.WINDOW_ABSENCE == "window_absence"
    assert VerificationStrategy.BROWSER_TAB_PRESENCE == "browser_tab_presence"
    assert VerificationStrategy.BROWSER_URL_MATCH == "browser_url_match"
    assert VerificationStrategy.DOM_STATE_CHANGE == "dom_state_change"
    assert VerificationStrategy.DOM_VALUE_MATCH == "dom_value_match"
    assert VerificationStrategy.FILESYSTEM_CHECK == "filesystem_check"


def test_intent_compiler_uses_canonical_verification():
    """Verify that intent compiler emits canonical UIA_READBACK instead of removed UI_STATE_CHANGE."""
    from app.planning.intent_compiler import UniversalPlanCompiler
    compiler = UniversalPlanCompiler()
    ctx = ExecutionContext(task_id="test-verif-strat")
    action, domain = compiler.compile_clause("click Save button", TargetDomain.APP, ctx)
    assert action is not None
    assert action.verification_strategy == VerificationStrategy.UIA_READBACK


# =============================================================================
# 2. Conversational Routing & Fast Lane Isolation Tests
# =============================================================================

@pytest.mark.parametrize(
    "query",
    [
        "Tell me a fact.",
        "Tell me something interesting.",
        "How are you?",
        "Tell me about Jaypee University.",
        "What is the capital of France?",
        "Can you write a short poem?",
        "Why is the sky blue?",
    ],
)
def test_conversational_queries_routed_outside_computer_agent(query: str):
    """Verify all conversational and knowledge queries route to conversation domain without computer agent."""
    decision = FRONT_DOOR_ROUTER.route(query)
    assert decision.domain in (IntentDomain.CONVERSATION, IntentDomain.KNOWLEDGE)
    assert decision.requires_computer_agent is False


# =============================================================================
# 3. File Explorer Physical Verification Tests
# =============================================================================

def test_file_explorer_window_presence_verification():
    """Verify File Explorer matches Windows 10 and Windows 11 window classes via discovery metadata."""
    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = [
        {"hwnd": 12345, "title": "Downloads", "pid": 4567, "class_name": "CabinetWClass"},
    ]
    verifier = VerificationEngine(uia_engine=mock_uia)
    res = verifier.verify_action(
        strategy=VerificationStrategy.WINDOW_PRESENCE,
        expected_state="File Explorer",
        target="file explorer",
        metadata={"window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["file explorer", "explorer", "downloads", "home"]},
        timeout_seconds=0.5,
    )
    assert res.verified is True
    assert "Downloads" in res.message


def test_file_explorer_win11_island_window_verification():
    """Verify File Explorer matches Windows 11 XamlExplorerHostIslandWindow via discovery metadata."""
    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = [
        {"hwnd": 67890, "title": "Home", "pid": 4567, "class_name": "XamlExplorerHostIslandWindow"},
    ]
    verifier = VerificationEngine(uia_engine=mock_uia)
    res = verifier.verify_action(
        strategy=VerificationStrategy.WINDOW_PRESENCE,
        expected_state="File Explorer",
        target="file explorer",
        metadata={"window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["file explorer", "explorer", "downloads", "home"]},
        timeout_seconds=0.5,
    )
    assert res.verified is True


# =============================================================================
# 4. Generic Browser Interaction Pipeline Tests
# =============================================================================

def test_site_search_decomposed_into_generic_interaction_pipeline():
    """Verify 'Search for X on Y' compiles into generic navigation, typing, and submission."""
    ctx = ExecutionContext(task_id="test-browser-pipeline")
    plan = CAPABILITY_ROUTER.plan_request("Search for MrBeast on YouTube", ctx)
    assert len(plan.steps) == 3

    # Step 1: Navigate to target site
    assert plan.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "youtube.com" in plan.steps[0].action.target

    # Step 2: Type query into semantic search box
    assert plan.steps[1].action.capability == CapabilityType.WEB_TYPE
    assert plan.steps[1].action.parameters.get("text") == "MrBeast"

    # Step 3: Press enter
    assert plan.steps[2].action.capability == CapabilityType.KEYBOARD_PRESS
    assert plan.steps[2].action.parameters.get("key") == "enter"


def test_google_search_decomposed_into_generic_interaction_pipeline():
    """Verify 'Search for OpenAI on Google' compiles into generic navigation and typing."""
    ctx = ExecutionContext(task_id="test-google-pipeline")
    plan = CAPABILITY_ROUTER.plan_request("Search for OpenAI on Google", ctx)
    assert len(plan.steps) == 3
    assert plan.steps[0].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "google.com" in plan.steps[0].action.target
    assert plan.steps[1].action.capability == CapabilityType.WEB_TYPE
    assert plan.steps[1].action.parameters.get("text") == "OpenAI"
    assert plan.steps[2].action.capability == CapabilityType.KEYBOARD_PRESS


def test_open_browser_resolves_generic_browser_application():
    """Verify 'Open browser and navigate to github.com' does not throw TARGET_NOT_FOUND."""
    ctx = ExecutionContext(task_id="test-open-browser")
    plan = CAPABILITY_ROUTER.plan_request("Open browser and navigate to github.com", ctx)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[0].action.target == "browser"
    assert plan.steps[1].action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "github.com" in plan.steps[1].action.target


# =============================================================================
# 5. Browser 404 & HTTP Error Classification Tests
# =============================================================================

@pytest.mark.anyio
async def test_browser_navigation_404_classified_as_failure():
    """Verify navigation returning HTTP 404 is classified as failure rather than false success."""
    from app.subsystems.computer.browser_engine import BrowserEngine

    engine = BrowserEngine()
    mock_page = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_page.goto.return_value = mock_resp
    mock_page.is_closed.return_value = False
    mock_page.url = "https://example.org/nonexistent_page_404"
    mock_page.title = AsyncMock(return_value="404 Not Found")

    with patch.object(engine, "_ensure_playwright", return_value=mock_page):
        res = await engine.navigate("https://example.org/nonexistent_page_404")
        assert res["success"] is False
        assert "HTTP_ERROR_404" in res["error"]
        assert res["status_code"] == 404


# =============================================================================
# 6. Task Cancellation Lifecycle Tests
# =============================================================================

@pytest.mark.anyio
async def test_task_cancellation_emits_clean_done_event():
    """Verify cancelled tasks yield a 'done' event with status='CANCELLED' and do not fail with unhandled errors."""
    from app.core.agent_loop import UniversalAgentLoop
    from app.core.contracts import ExecutionContext, Plan, PlanStep, Action, CapabilityType, VerificationStrategy
    from app.models import Task

    mock_db = MagicMock()
    mock_event_bus = MagicMock()
    mock_router = MagicMock()
    mock_verifier = MagicMock()

    loop = UniversalAgentLoop(
        router=mock_router,
        verifier=mock_verifier,
        event_bus=mock_event_bus,
    )

    task = Task(id="test-cancel-task", session_id="test-session", request="Open Calculator")
    ctx = ExecutionContext(task_id=task.id)
    ctx.mark_cancelled("User requested stop")

    mock_router.plan_request.return_value = Plan(
        task_id=task.id,
        steps=[PlanStep(step_number=1, description="Open Calc", action=Action(capability=CapabilityType.APP_LAUNCH, target="calc"))],
    )

    events = []
    async for ev_type, ev_data in loop.run(mock_db, task, ctx):
        events.append((ev_type, ev_data))

    assert any(ev_type == "done" and ev_data.get("status") == "CANCELLED" for ev_type, ev_data in events)
    assert task.status == TaskState.CANCELLED.value
