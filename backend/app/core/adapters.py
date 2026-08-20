"""PLUTON V2 — Core Contract Adapters.

Provides bidirectional adapters and compatibility translation between:
- Canonical Task, Goal, Plan, Action, and Verification models
- Legacy dictionary formats and string-based representations
- Backward-compatible security / permission mappings.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from .contracts import (
    Action,
    CapabilityDescriptor,
    CapabilityType,
    ContextReference,
    Entity,
    EntityType,
    ExecutionTier,
    Goal,
    GoalConstraint,
    IntentDomain,
    Plan,
    PlanStep,
    ReferenceType,
    RiskLevel,
    SideEffectLevel,
    TargetDomain,
    Task,
    TaskBudget,
    TaskChannel,
    TaskState,
    VerificationOutcome,
    VerificationResult,
    VerificationStrategy,
)


class Permission(str, Enum):
    """Legacy backward-compatible permission level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def adapt_permission_to_risk(permission: Permission | str) -> RiskLevel:
    """Maps legacy Permission enum or strings to canonical RiskLevel."""
    if isinstance(permission, Permission):
        val = permission.value
    elif hasattr(permission, "value"):
        val = permission.value
    else:
        val = str(permission)

    val_lower = val.lower()
    if val_lower == "low":
        return RiskLevel.LOW
    elif val_lower == "medium":
        return RiskLevel.MEDIUM
    elif val_lower in ("high", "critical"):
        return RiskLevel.HIGH
    return RiskLevel.LOW


def adapt_risk_to_permission(risk: RiskLevel | str) -> Permission:
    """Maps canonical RiskLevel to legacy Permission enum."""
    if isinstance(risk, RiskLevel):
        val = risk.value
    elif hasattr(risk, "value"):
        val = risk.value
    else:
        val = str(risk)

    val_upper = val.upper()
    if val_upper == "LOW":
        return Permission.LOW
    elif val_upper == "MEDIUM":
        return Permission.MEDIUM
    elif val_upper in ("HIGH", "CRITICAL"):
        return Permission.HIGH
    return Permission.LOW


class ContractAdapter:
    """Universal contract adapter ensuring seamless data model transitions."""

    @staticmethod
    def task_to_dict(task: Task) -> dict[str, Any]:
        return task.to_dict()

    @staticmethod
    def task_from_dict(data: dict[str, Any]) -> Task:
        return Task.from_dict(data)

    @staticmethod
    def plan_to_dict(plan: Plan) -> dict[str, Any]:
        return plan.to_dict()

    @staticmethod
    def plan_from_dict(data: dict[str, Any]) -> Plan:
        return Plan.from_dict(data)

    @staticmethod
    def action_to_dict(action: Action) -> dict[str, Any]:
        return action.to_dict()

    @staticmethod
    def action_from_dict(data: dict[str, Any]) -> Action:
        return Action.from_dict(data)

    @staticmethod
    def goal_to_dict(goal: Goal) -> dict[str, Any]:
        return goal.to_dict()

    @staticmethod
    def goal_from_dict(data: dict[str, Any]) -> Goal:
        return Goal.from_dict(data)

    @staticmethod
    def adapt_legacy_action(legacy_dict: dict[str, Any]) -> Action:
        """Adapts a raw dictionary or legacy action payload into canonical Action."""
        return Action.from_dict(legacy_dict)

    @staticmethod
    def adapt_legacy_plan(task_id: str, steps_data: list[dict[str, Any]]) -> Plan:
        """Constructs a canonical Plan from a list of legacy step dicts."""
        plan_steps = []
        for idx, s in enumerate(steps_data, start=1):
            act_data = s.get("action", s)
            action = Action.from_dict(act_data)
            step = PlanStep(
                step_number=s.get("step_number", idx),
                description=s.get("description", f"Step {idx}"),
                action=action,
                dependencies=s.get("dependencies", []),
            )
            plan_steps.append(step)
        return Plan(task_id=task_id, steps=plan_steps)
