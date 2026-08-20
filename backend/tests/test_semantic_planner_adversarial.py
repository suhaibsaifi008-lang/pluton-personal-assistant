"""
PLUTON V2 — Semantic Planner Adversarial & Safety Validation Test Suite.
Ensures malformed plans, fabricated HWNDs/PIDs, cyclic dependencies, missing targets,
and unverified mutating operations are strictly rejected by the deterministic validator.
"""

import pytest
from app.planning.semantic import (
    SemanticIntent,
    SemanticPlan,
    SemanticPlanValidator,
    SemanticStep,
    TargetReference,
    TargetReferenceType,
)


def test_reject_empty_plan_without_conversational_flag():
    """An operational plan with 0 steps must be rejected."""
    plan = SemanticPlan(goal="Do something", is_conversational=False, steps=[])
    errors = SemanticPlanValidator.validate_plan(plan)
    assert any("EMPTY_PLAN" in e for e in errors)


def test_reject_duplicate_step_ids():
    """Duplicate step IDs must be rejected."""
    s1 = SemanticStep(
        step_id=1,
        intent=SemanticIntent.OPEN_APPLICATION,
        capability="app.launch",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="Notepad"),
    )
    s2 = SemanticStep(
        step_id=1,
        intent=SemanticIntent.INPUT_TEXT,
        capability="keyboard.type",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="Notepad"),
        parameters={"text": "hello"},
    )
    plan = SemanticPlan(goal="Duplicate steps test", steps=[s1, s2])
    errors = SemanticPlanValidator.validate_plan(plan)
    assert any("DUPLICATE_STEP_ID" in e for e in errors)


def test_reject_unknown_capability():
    """Unregistered or hallucinated capabilities must be rejected."""
    s1 = SemanticStep(
        step_id=1,
        intent=SemanticIntent.OPEN_APPLICATION,
        capability="quantum.teleport_process",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="App"),
    )
    plan = SemanticPlan(goal="Unknown cap test", steps=[s1])
    errors = SemanticPlanValidator.validate_plan(plan)
    assert any("UNKNOWN_CAPABILITY" in e for e in errors)


def test_reject_fabricated_physical_identifiers():
    """Model-generated synthetic HWNDs or PIDs must be rejected to prevent hallucinated targeting."""
    s1 = SemanticStep(
        step_id=1,
        intent=SemanticIntent.INPUT_TEXT,
        capability="keyboard.type",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="Window"),
        parameters={"text": "test", "hwnd": 999999, "pid": 1234},
    )
    plan = SemanticPlan(goal="Fabricated HWND test", steps=[s1])
    errors = SemanticPlanValidator.validate_plan(plan)
    assert any("FABRICATED_PHYSICAL_ID" in e for e in errors)


def test_reject_action_as_target_conflation():
    """Target references containing action verbs must be rejected."""
    s1 = SemanticStep(
        step_id=1,
        intent=SemanticIntent.OPEN_APPLICATION,
        capability="app.launch",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="calculate 125 multiplied by 48"),
    )
    plan = SemanticPlan(goal="Action as target test", steps=[s1])
    errors = SemanticPlanValidator.validate_plan(plan)
    assert any("ACTION_AS_TARGET" in e for e in errors)


def test_reject_cyclic_step_dependencies():
    """Step dependencies with circular references must be rejected."""
    s1 = SemanticStep(
        step_id=1,
        intent=SemanticIntent.OPEN_APPLICATION,
        capability="app.launch",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="App1"),
        dependencies=[2],
    )
    s2 = SemanticStep(
        step_id=2,
        intent=SemanticIntent.OPEN_APPLICATION,
        capability="app.launch",
        target_reference=TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference="App2"),
        dependencies=[1],
    )
    plan = SemanticPlan(goal="Cycle test", steps=[s1, s2])
    errors = SemanticPlanValidator.validate_plan(plan)
    assert any("INVALID_DEPENDENCY" in e or "CYCLIC_DEPENDENCIES" in e for e in errors)