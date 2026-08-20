"""PLUTON V2 — Front-Door Task Router & Fast Plane Verification Suite (Milestone 2).

Exhaustive tests covering:
- Conversation and Knowledge Fast Lane routing (zero computer execution)
- Trusted Date and Time deterministic fast capability
- Trusted Arithmetic AST Evaluator fast capability
- Computer and Multi-Domain routing for physical desktop tasks
- Ambiguity and safety fallback
- Permanent historical failure regression verification
- Sub-millisecond router and fast capability performance benchmarks
"""

from datetime import datetime, timezone
import time
import pytest

from app.core.contracts import IntentDomain, Task, TaskChannel
from app.fast_plane import FastCapabilityExecutor, SafeMathEvaluator, SystemClockEvaluator
from app.router import FRONT_DOOR_ROUTER, FrontDoorTaskRouter, RouteContext, RouteDecision


# =============================================================================
# 1. Conversation & Knowledge Fast Lane Tests
# =============================================================================

@pytest.mark.parametrize("query", [
    "Tell me a fact.",
    "Tell me a funny joke.",
    "Good morning! How are you doing today?",
    "Explain how black holes work.",
    "What is the theory of general relativity?",
    "Can you write a short poem about space exploration?",
    "Why is the sky blue?",
    "Define quantum entanglement in simple terms.",
])
def test_conversation_fast_lane_never_requires_computer_agent(query: str):
    decision = FRONT_DOOR_ROUTER.route(query)
    assert decision.domain in (IntentDomain.CONVERSATION, IntentDomain.KNOWLEDGE)
    assert decision.requires_computer_agent is False
    assert decision.capability_id is None


# =============================================================================
# 2. Trusted Date / Time Fast Capability Tests
# =============================================================================

@pytest.mark.parametrize("query", [
    "What is today's date?",
    "what is the current time?",
    "what time is it",
    "tell me the date today",
    "current date",
    "current time",
    "what is today's date",
])
def test_trusted_date_time_routing(query: str):
    decision = FRONT_DOOR_ROUTER.route(query)
    assert decision.domain == IntentDomain.TRUSTED_DATA
    assert decision.capability_id == "system.time"
    assert decision.requires_computer_agent is False
    assert decision.requires_current_data is True


def test_system_clock_evaluator_execution():
    res = SystemClockEvaluator.get_current_time()
    assert res["success"] is True
    assert "datetime_iso" in res
    assert "formatted_date" in res
    assert "formatted_time" in res
    assert "timestamp_unix" in res
    assert str(datetime.now(timezone.utc).year) in res["formatted_date"]


def test_system_clock_timezone_evaluation():
    res_tokyo = SystemClockEvaluator.get_current_time("Asia/Tokyo")
    assert res_tokyo["success"] is True
    assert res_tokyo["timezone"] == "Asia/Tokyo"

    res_est = SystemClockEvaluator.get_current_time("EST")
    assert res_est["success"] is True
    assert "America/New_York" in res_est["timezone"] or res_est["timezone"] == "EST"

    res_invalid = SystemClockEvaluator.get_current_time("INVALID_PLANET_TZ")
    assert res_invalid["success"] is False
    assert "Invalid or unrecognized timezone" in res_invalid["error"]


# =============================================================================
# 3. Trusted Calculation Fast Capability Tests
# =============================================================================

@pytest.mark.parametrize("query,expected_val", [
    ("What is 25 * 48?", 1200),
    ("calculate 1500 * 0.18", 270),
    ("compute 125 + 375", 500),
    ("what is (50 + 50) * 2", 200),
    ("20% of 1000", 200),
    ("solve 100 - 45", 55),
    ("evaluate 2^3", 8),
    ("-5 * 10", -50),
    ("100 / 4", 25),
])
def test_trusted_calculation_routing_and_eval(query: str, expected_val: float):
    decision = FRONT_DOOR_ROUTER.route(query)
    assert decision.domain == IntentDomain.CALCULATION
    assert decision.capability_id == "general.calculate"
    assert decision.requires_computer_agent is False

    fast_res = FastCapabilityExecutor.execute(decision.capability_id, decision.parameters)
    assert fast_res["success"] is True
    assert float(fast_res["result"]) == float(expected_val)


def test_calculation_invalid_and_division_by_zero():
    div_zero = SafeMathEvaluator.evaluate("100 / 0")
    assert div_zero["success"] is False
    assert "Division by zero" in div_zero["error"]

    empty_expr = SafeMathEvaluator.evaluate("")
    assert empty_expr["success"] is False
    assert "Expression cannot be empty" in empty_expr["error"]

    invalid_chars = SafeMathEvaluator.evaluate("hello + world")
    assert invalid_chars["success"] is False
    assert "Invalid mathematical expression" in invalid_chars["error"]


# =============================================================================
# 4. Computer & Multi-Domain Routing Tests
# =============================================================================

def test_application_operations_route_to_computer_agent():
    d1 = FRONT_DOOR_ROUTER.route("Open Calculator")
    assert d1.requires_computer_agent is True
    assert d1.domain == IntentDomain.COMPUTER

    d2 = FRONT_DOOR_ROUTER.route("Launch Notepad and prepare to write")
    assert d2.requires_computer_agent is True
    assert d2.domain == IntentDomain.COMPUTER

    d3 = FRONT_DOOR_ROUTER.route("Close Spotify window")
    assert d3.requires_computer_agent is True
    assert d3.domain == IntentDomain.COMPUTER


def test_browser_operations_route_to_browser_domain():
    d = FRONT_DOOR_ROUTER.route("Open browser and navigate to https://github.com")
    assert d.requires_computer_agent is True
    assert d.domain == IntentDomain.BROWSER


def test_filesystem_operations_route_to_filesystem_domain():
    d = FRONT_DOOR_ROUTER.route("Create file summary.txt in workspace")
    assert d.requires_computer_agent is True
    assert d.domain == IntentDomain.FILESYSTEM


def test_terminal_operations_route_to_terminal_domain():
    d = FRONT_DOOR_ROUTER.route("Execute command in terminal: dir")
    assert d.requires_computer_agent is True
    assert d.domain == IntentDomain.TERMINAL


def test_multi_domain_compound_intent():
    d = FRONT_DOOR_ROUTER.route("Open Calculator and calculate 25 * 48")
    assert d.requires_computer_agent is True
    assert d.domain == IntentDomain.MULTI_DOMAIN


# =============================================================================
# 5. Permanent Historical Regression Tests (Part 20)
# =============================================================================

def test_regression_1_tell_me_a_fact_never_computer_action():
    """Historical Bug 1: 'tell me a fact' entered computer UI execution."""
    d = FRONT_DOOR_ROUTER.route("Tell me a fact.")
    assert d.requires_computer_agent is False
    assert d.domain in (IntentDomain.CONVERSATION, IntentDomain.KNOWLEDGE)


def test_regression_2_what_is_todays_date_uses_trusted_clock():
    """Historical Bug 2: Date questions were hallucinated by LLM."""
    d = FRONT_DOOR_ROUTER.route("what is today's date?")
    assert d.domain == IntentDomain.TRUSTED_DATA
    assert d.capability_id == "system.time"
    assert d.requires_computer_agent is False

    res = FastCapabilityExecutor.execute(d.capability_id, d.parameters)
    assert res["success"] is True
    assert str(datetime.now(timezone.utc).year) in res["formatted_date"]


def test_regression_3_calculation_does_not_type_into_foreground_window():
    """Historical Bug 3: Calculations typed into unrelated foreground windows."""
    d = FRONT_DOOR_ROUTER.route("what is 25 * 48?")
    assert d.domain == IntentDomain.CALCULATION
    assert d.capability_id == "general.calculate"
    assert d.requires_computer_agent is False

    res = FastCapabilityExecutor.execute(d.capability_id, d.parameters)
    assert res["result"] == 1200


def test_regression_4_open_calculator_reaches_computer_path():
    """Ensure desktop control intent reaches computer agent."""
    d = FRONT_DOOR_ROUTER.route("open Calculator")
    assert d.requires_computer_agent is True
    assert d.domain == IntentDomain.COMPUTER


def test_regression_5_open_file_explorer_reaches_computer_path():
    """Ensure file explorer reaches computer agent."""
    d = FRONT_DOOR_ROUTER.route("open File Explorer")
    assert d.requires_computer_agent is True
    assert d.domain in (IntentDomain.COMPUTER, IntentDomain.FILESYSTEM)


def test_regression_6_browser_navigation_remains_generic():
    """Browser request is generic and browser-neutral."""
    d = FRONT_DOOR_ROUTER.route("open the browser and navigate to a website")
    assert d.requires_computer_agent is True
    assert d.domain == IntentDomain.BROWSER


# =============================================================================
# 6. Ambiguity, Empty, and Task Object Tests
# =============================================================================

def test_empty_and_whitespace_requests_handled_safely():
    d1 = FRONT_DOOR_ROUTER.route("")
    assert d1.is_ambiguous is True
    assert d1.requires_computer_agent is False

    d2 = FRONT_DOOR_ROUTER.route("    \n\t  ")
    assert d2.is_ambiguous is True
    assert d2.requires_computer_agent is False


def test_task_model_input_routed_correctly():
    task = Task(user_request="Calculate 100 * 5", origin=TaskChannel.VOICE)
    d = FRONT_DOOR_ROUTER.route(task)
    assert d.task_id == task.task_id
    assert d.domain == IntentDomain.CALCULATION
    assert d.capability_id == "general.calculate"


# =============================================================================
# 7. 100-Case Deterministic Benchmark
# =============================================================================

def test_100_case_deterministic_router_latency_benchmark():
    test_queries = [
        "what is today's date?",
        "what time is it?",
        "what is 25 * 48?",
        "calculate 1500 * 0.18",
        "tell me a fact",
        "explain black holes",
        "open Calculator",
        "open File Explorer",
        "open browser and navigate to github",
        "create file notes.txt",
    ] * 10  # 100 iterations

    latencies_us = []
    for q in test_queries:
        t0 = time.perf_counter()
        d = FRONT_DOOR_ROUTER.route(q)
        if d.capability_id:
            _ = FastCapabilityExecutor.execute(d.capability_id, d.parameters)
        elapsed = (time.perf_counter() - t0) * 1_000_000.0
        latencies_us.append(elapsed)

    mean_us = sum(latencies_us) / len(latencies_us)
    sorted_lat = sorted(latencies_us)
    p95_us = sorted_lat[int(len(sorted_lat) * 0.95)]
    max_us = sorted_lat[-1]

    # Target: router + deterministic execution must be < 20ms (20,000 us), typical < 1ms
    assert mean_us < 20000.0, f"Mean latency {mean_us:.2f}us exceeded 20ms target"
    assert p95_us < 20000.0, f"P95 latency {p95_us:.2f}us exceeded 20ms target"
