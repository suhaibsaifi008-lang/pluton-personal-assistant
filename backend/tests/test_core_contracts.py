"""PLUTON V2 — Core Contracts & Type System Verification Suite (Milestone 1 Hardened).

Exhaustive tests covering:
- Explicit rejection of invalid enums across all domains (no silent reinterpretation)
- Strict numeric validation (budgets, latencies, confidences, steps, turn IDs)
- Strict datetime parsing and rejection of malformed timestamps
- Required string validation (non-empty, non-whitespace)
- Strict zero browser-name hardcoding (defaults remain None)
- Single canonical RiskLevel type on Action, CapabilityDescriptor, RiskLevelGrant
- Separation of semantic references from physical runtime bindings
- JSON serialization / deserialization round-trips
- Backward compatibility adapters
- Microsecond latency benchmarks (< 0.1ms)
"""

from datetime import datetime, timezone
import json
import time
from uuid import uuid4
import pytest

from app.core.contracts import (
    Action,
    Artifact,
    ArtifactType,
    BrowserTabIdentity,
    CapabilityDescriptor,
    CapabilityType,
    ContextReference,
    ContractValidationError,
    Entity,
    EntityType,
    Evidence,
    ExecutionContext,
    ExecutionTier,
    Failure,
    FailureCategory,
    Goal,
    GoalConstraint,
    IntentDomain,
    MemoryCategory,
    MemoryRecord,
    ObservationType,
    PermissionGrant,
    PermissionStatus,
    Plan,
    PlanStep,
    ReferenceType,
    RiskLevel,
    SideEffectLevel,
    TabSnapshot,
    TargetDomain,
    Task,
    TaskBudget,
    TaskChannel,
    TaskEvent,
    TaskState,
    VerificationOutcome,
    VerificationResult,
    VerificationStrategy,
    WindowSnapshot,
    WorkflowContext,
    WorldStateContract,
)
from app.core.adapters import ContractAdapter, Permission, adapt_permission_to_risk, adapt_risk_to_permission


# =============================================================================
# 1. Invalid Enum Rejection Tests (Explicit Validation Failure)
# =============================================================================

def test_invalid_intent_domain_rejected():
    with pytest.raises(ContractValidationError, match="intent_domain"):
        Goal.from_dict({"objective": "test_goal", "intent_domain": "INVALID_DOMAIN_123"})


def test_invalid_capability_type_rejected():
    with pytest.raises(ContractValidationError, match="capability"):
        Action.from_dict({"capability": "non_existent_domain.fake_action"})


def test_invalid_reference_type_rejected():
    with pytest.raises(ContractValidationError, match="ref_type"):
        ContextReference.from_dict({"ref_type": "BOGUS_REF_TYPE"})


def test_invalid_entity_type_rejected():
    with pytest.raises(ContractValidationError, match="entity_type"):
        Entity.from_dict({"semantic_name": "report", "entity_type": "UNKNOWN_ENTITY_TYPE"})


def test_invalid_verification_strategy_rejected():
    with pytest.raises(ContractValidationError, match="strategy"):
        VerificationResult.from_dict({"strategy": "MAGIC_VERIFICATION", "verified": True})


def test_invalid_risk_level_rejected():
    with pytest.raises(ContractValidationError, match="risk_level"):
        Action.from_dict({"capability": "app.launch", "risk_level": "EXTREME_DANGER"})


def test_invalid_task_state_rejected():
    with pytest.raises(ContractValidationError, match="status"):
        Task.from_dict({"user_request": "hello", "status": "NON_EXISTENT_STATE"})


def test_invalid_task_channel_rejected():
    with pytest.raises(ContractValidationError, match="origin"):
        Task.from_dict({"user_request": "hello", "origin": "TELEPATHY"})


def test_invalid_side_effect_level_rejected():
    with pytest.raises(ContractValidationError, match="side_effect_level"):
        CapabilityDescriptor.from_dict({
            "capability_id": "app.launch",
            "name": "Launch App",
            "side_effect_level": "DESTRUCTIVE_CHAOS"
        })


def test_invalid_failure_category_rejected():
    with pytest.raises(ContractValidationError, match="category"):
        Failure.from_dict({"message": "Error occurred", "category": "COSMIC_RAY_BITFLIP"})


def test_invalid_observation_type_rejected():
    with pytest.raises(ContractValidationError, match="observation_type"):
        Evidence.from_dict({
            "source": "sensor",
            "observation_type": "MAGIC_OBSERVATION",
            "observed_value": {}
        })


# =============================================================================
# 2. Strict Numeric Validation Tests
# =============================================================================

def test_negative_budget_values_rejected():
    with pytest.raises(ContractValidationError, match="max_steps"):
        TaskBudget(max_steps=-1)

    with pytest.raises(ContractValidationError, match="max_time_seconds"):
        TaskBudget(max_time_seconds=-10.0)

    with pytest.raises(ContractValidationError, match="max_cost_usd"):
        TaskBudget(max_cost_usd=-0.5)


def test_evidence_confidence_bounds_enforced():
    # Confidence > 1.0 rejected
    with pytest.raises(ContractValidationError, match="confidence"):
        Evidence(source="win32", observation_type=ObservationType.WINDOW_INSPECTION, observed_value={}, confidence=1.5)

    # Confidence < 0.0 rejected
    with pytest.raises(ContractValidationError, match="confidence"):
        Evidence(source="win32", observation_type=ObservationType.WINDOW_INSPECTION, observed_value={}, confidence=-0.1)


def test_negative_latency_rejected():
    with pytest.raises(ContractValidationError, match="latency_ms"):
        VerificationResult(verified=True, latency_ms=-5.0)


def test_non_positive_action_timeout_rejected():
    with pytest.raises(ContractValidationError, match="timeout_seconds"):
        Action(capability=CapabilityType.APP_LAUNCH, timeout_seconds=0.0)

    with pytest.raises(ContractValidationError, match="timeout_seconds"):
        Action(capability=CapabilityType.APP_LAUNCH, timeout_seconds=-10.0)


def test_invalid_step_number_and_dependencies_rejected():
    action = Action(capability=CapabilityType.APP_LAUNCH)

    with pytest.raises(ContractValidationError, match="step_number"):
        PlanStep(step_number=0, description="Step zero", action=action)

    with pytest.raises(ContractValidationError, match="dependency"):
        PlanStep(step_number=1, description="Step one", action=action, dependencies=[0])

    with pytest.raises(ContractValidationError, match="dependency"):
        PlanStep(step_number=1, description="Step one", action=action, dependencies=[-1])


def test_invalid_task_turn_id_rejected():
    with pytest.raises(ContractValidationError, match="turn_id"):
        Task(user_request="test", turn_id=0)

    with pytest.raises(ContractValidationError, match="turn_id"):
        Task(user_request="test", turn_id=-3)


# =============================================================================
# 3. Datetime Validation Tests
# =============================================================================

def test_malformed_timestamp_rejected():
    with pytest.raises(ContractValidationError, match="timestamp"):
        Evidence.from_dict({
            "source": "win32",
            "observation_type": "window_inspection",
            "observed_value": {},
            "timestamp": "NOT_A_REAL_DATE_STRING"
        })

    with pytest.raises(ContractValidationError, match="created_at"):
        Task.from_dict({
            "user_request": "Open browser",
            "created_at": "yesterday at 5pm"
        })


def test_datetime_is_timezone_aware():
    task = Task(user_request="Check time")
    assert task.created_at.tzinfo is not None
    assert task.created_at.tzinfo == timezone.utc

    ev = Evidence(source="test", observation_type=ObservationType.WINDOW_INSPECTION, observed_value={})
    assert ev.timestamp.tzinfo is not None
    assert ev.timestamp.tzinfo == timezone.utc


# =============================================================================
# 4. Required String Validation Tests
# =============================================================================

def test_empty_required_strings_rejected():
    # Task user_request cannot be empty or whitespace
    with pytest.raises(ContractValidationError, match="user_request"):
        Task(user_request="")

    with pytest.raises(ContractValidationError, match="user_request"):
        Task(user_request="   \n\t  ")

    # Goal objective cannot be empty
    with pytest.raises(ContractValidationError, match="objective"):
        Goal(objective="")

    # CapabilityDescriptor capability_id & name cannot be empty
    with pytest.raises(ContractValidationError, match="capability_id"):
        CapabilityDescriptor(capability_id="", name="Test", domain=IntentDomain.COMPUTER, description="")

    with pytest.raises(ContractValidationError, match="name"):
        CapabilityDescriptor(capability_id="test.id", name="", domain=IntentDomain.COMPUTER, description="")

    # Evidence source cannot be empty
    with pytest.raises(ContractValidationError, match="source"):
        Evidence(source="", observation_type=ObservationType.WINDOW_INSPECTION, observed_value={})

    # Failure message cannot be empty
    with pytest.raises(ContractValidationError, match="message"):
        Failure(message="")


# =============================================================================
# 5. Zero Browser Defaults Regression Test
# =============================================================================

def test_zero_browser_defaults():
    # WorkflowContext must default active_browser to None
    wc = WorkflowContext()
    assert wc.active_browser is None, f"WorkflowContext.active_browser default must be None, got {wc.active_browser}"

    # BrowserTabIdentity must default browser_name to None
    tab_id = BrowserTabIdentity()
    assert tab_id.browser_name is None, f"BrowserTabIdentity.browser_name default must be None, got {tab_id.browser_name}"

    # ExecutionContext must default active_browser to None
    ec = ExecutionContext(task_id="task-123")
    assert ec.active_browser is None, f"ExecutionContext.active_browser default must be None, got {ec.active_browser}"

    # TabSnapshot must default browser_name to None
    tab_snap = TabSnapshot(tab_id="tab-1", title="Title", url="about:blank")
    assert tab_snap.browser_name is None, f"TabSnapshot.browser_name default must be None, got {tab_snap.browser_name}"


# =============================================================================
# 6. Single Canonical Risk Hierarchy & Adapter Tests
# =============================================================================

def test_canonical_risk_level_on_action_and_descriptor():
    action = Action(capability=CapabilityType.FILESYSTEM_DELETE, risk_level=RiskLevel.HIGH)
    assert action.risk_level == RiskLevel.HIGH
    assert isinstance(action.risk_level, RiskLevel)

    cap = CapabilityDescriptor(
        capability_id="filesystem.delete",
        name="Delete File",
        domain=IntentDomain.FILESYSTEM,
        description="Delete file",
        risk_level=RiskLevel.CRITICAL
    )
    assert cap.risk_level == RiskLevel.CRITICAL
    assert isinstance(cap.risk_level, RiskLevel)

    grant = PermissionGrant(capability_id="filesystem.delete", risk_level=RiskLevel.HIGH, status=PermissionStatus.GRANTED)
    assert grant.risk_level == RiskLevel.HIGH
    assert grant.status == PermissionStatus.GRANTED


def test_permission_adapter_mapping():
    assert adapt_permission_to_risk(Permission.LOW) == RiskLevel.LOW
    assert adapt_permission_to_risk(Permission.MEDIUM) == RiskLevel.MEDIUM
    assert adapt_permission_to_risk(Permission.HIGH) == RiskLevel.HIGH

    assert adapt_risk_to_permission(RiskLevel.LOW) == Permission.LOW
    assert adapt_risk_to_permission(RiskLevel.MEDIUM) == Permission.MEDIUM
    assert adapt_risk_to_permission(RiskLevel.HIGH) == Permission.HIGH
    assert adapt_risk_to_permission(RiskLevel.CRITICAL) == Permission.HIGH


# =============================================================================
# 7. Semantic vs Runtime Target Separation
# =============================================================================

def test_semantic_reference_separated_from_runtime_binding():
    # Model generates semantic reference with NO physical binding
    unbound_ref = ContextReference(
        ref_type=ReferenceType.ACTIVE_WINDOW,
        raw_reference="the open window",
        entity_type=EntityType.WINDOW
    )
    assert unbound_ref.runtime_target_binding is None
    assert unbound_ref.is_runtime_bound is False

    # TargetResolver supplies the trusted physical binding
    bound_ref = ContextReference(
        ref_type=ReferenceType.ACTIVE_WINDOW,
        raw_reference="the open window",
        entity_type=EntityType.WINDOW,
        runtime_target_binding="hwnd:98765",
        is_runtime_bound=True
    )
    assert bound_ref.runtime_target_binding == "hwnd:98765"
    assert bound_ref.is_runtime_bound is True


# =============================================================================
# 8. JSON Serialization Round-Trips
# =============================================================================

def test_task_and_goal_round_trip():
    goal = Goal(
        objective="calculate_vat",
        intent_domain=IntentDomain.CALCULATION,
        parameters={"amount": 1000, "rate": 0.20},
        constraints=[GoalConstraint(constraint_type="precision", description="2 decimal places", value=2)],
        desired_outcome="Result 200.00"
    )
    task = Task(
        user_request="Calculate 20% VAT on $1000",
        session_id="sess-001",
        origin=TaskChannel.TEXT,
        status=TaskState.READY,
        goal=goal,
        budget=TaskBudget(max_steps=3, max_time_seconds=30.0)
    )

    t_dict = task.to_dict()
    restored = Task.from_dict(json.loads(json.dumps(t_dict)))

    assert restored.task_id == task.task_id
    assert restored.user_request == task.user_request
    assert restored.origin == TaskChannel.TEXT
    assert restored.status == TaskState.READY
    assert restored.goal is not None
    assert restored.goal.objective == "calculate_vat"
    assert restored.goal.intent_domain == IntentDomain.CALCULATION
    assert len(restored.goal.constraints) == 1
    assert restored.goal.constraints[0].value == 2


def test_plan_and_action_round_trip():
    action = Action(
        capability=CapabilityType.APP_LAUNCH,
        target="calc.exe",
        parameters={"path": "calc.exe"},
        target_domain=TargetDomain.APP,
        risk_level=RiskLevel.MEDIUM,
        verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
    )
    step = PlanStep(step_number=1, description="Launch calculator", action=action)
    plan = Plan(task_id="task-123", steps=[step])

    p_dict = plan.to_dict()
    restored_plan = Plan.from_dict(json.loads(json.dumps(p_dict)))

    assert restored_plan.task_id == "task-123"
    assert len(restored_plan.steps) == 1
    assert restored_plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert restored_plan.steps[0].action.risk_level == RiskLevel.MEDIUM


# =============================================================================
# 9. Latency Benchmark (< 0.1ms)
# =============================================================================

def test_contract_instantiation_latency():
    iterations = 5000
    t0 = time.perf_counter()
    for _ in range(iterations):
        task = Task(
            user_request="Benchmark test request",
            goal=Goal(objective="test_bench", intent_domain=IntentDomain.COMPUTER),
            budget=TaskBudget(max_steps=10),
        )
        _ = task.to_dict()
    elapsed_ms = ((time.perf_counter() - t0) * 1000) / iterations

    assert elapsed_ms < 0.1, f"Contract creation latency {elapsed_ms:.4f}ms exceeded 0.1ms target"
