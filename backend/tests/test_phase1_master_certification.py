"""
PLUTON V2 — Master Phase 1 Certification Test Suite
Validates generic intent compilation, action vs target separation, arithmetic calculation execution,
browser navigation, verification intent compilation, multi-process app window binding, and zero hardcoding.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TargetDomain,
    TaskState,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)
from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER, UniversalAppRegistry
from app.subsystems.computer.domains.app import AppDomainHandler, _get_process_image_name
from app.subsystems.computer.target_resolver import TARGET_RESOLVER, TargetResolver


def test_failure_a_calculator_action_vs_target_separation():
    """Verify 'Open Calculator and calculate 125 multiplied by 48' compiles without TargetResolver confusion."""
    ctx = ExecutionContext(task_id="cert-calc")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open Calculator and calculate 125 multiplied by 48.", ctx)

    assert len(plan.steps) == 2
    step1, step2 = plan.steps[0], plan.steps[1]

    # Step 1: Launch Calculator
    assert step1.action.capability == CapabilityType.APP_LAUNCH
    assert step1.action.target.lower() in ("calculator", "calc")

    # Step 2: Action must NOT be routed as a fake target!
    assert step2.action.capability == CapabilityType.KEYBOARD_TYPE
    assert step2.action.target.lower() in ("calculator", "calc")
    assert step2.action.parameters.get("text") == "125*48="
    assert step2.action.expected_state == "6000"


@pytest.mark.parametrize(
    "query, expected_text, expected_res",
    [
        ("calculate 25 + 75", "25+75=", "100"),
        ("compute 100 times 5", "100*5=", "500"),
        ("calculate 500 divided by 2", "500/2=", "250.0"),
        ("calculate 1000 minus 250", "1000-250=", "750"),
        ("solve (50 + 50) * 2", "(50+50)*2=", "200"),
    ],
)
def test_generic_arithmetic_expressions(query: str, expected_text: str, expected_res: str):
    """Verify arbitrary arithmetic expressions compile generically without hardcoding."""
    ctx = ExecutionContext(task_id="cert-math")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan(query, ctx)

    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.action.capability == CapabilityType.KEYBOARD_TYPE
    assert step.action.parameters.get("text") == expected_text
    assert step.action.expected_state == expected_res


def test_failure_b_browser_launch_navigate_and_verify_separation():
    """Verify 'Open Chrome, navigate to youtube.com, and verify that YouTube opened' compiles to 3 distinct steps."""
    ctx = ExecutionContext(task_id="cert-chrome")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open Chrome, navigate to youtube.com, and verify that YouTube opened.", ctx)

    assert len(plan.steps) == 3
    step1, step2, step3 = plan.steps[0], plan.steps[1], plan.steps[2]

    # Step 1: Open Chrome
    assert step1.action.capability == CapabilityType.APP_LAUNCH
    assert step1.action.target.lower() == "chrome"

    # Step 2: Navigate to youtube.com
    assert step2.action.capability == CapabilityType.BROWSER_NAVIGATE
    assert "youtube.com" in step2.action.target.lower() or "youtube.com" in step2.action.parameters.get("url", "").lower()

    # Step 3: Verify YouTube opened
    assert step3.action.capability == CapabilityType.BROWSER_GET_TITLE
    assert "youtube" in step3.action.target.lower()


def test_generic_app_registry_exact_matching():
    """Verify UniversalAppRegistry never matches partial verbs like 'calc' inside 'calculate'."""
    assert UniversalAppRegistry.resolve("calculator") is not None
    assert UniversalAppRegistry.resolve("calc") is not None
    assert UniversalAppRegistry.resolve("calculate 125 multiplied by 48") is None
    assert UniversalAppRegistry.resolve("close window") is None


def test_win32_process_image_name_retrieval():
    """Verify _get_process_image_name safely retrieves process names using Win32 API."""
    import os
    current_pid = os.getpid()
    pname = _get_process_image_name(current_pid)
    assert "python" in pname or "pytest" in pname