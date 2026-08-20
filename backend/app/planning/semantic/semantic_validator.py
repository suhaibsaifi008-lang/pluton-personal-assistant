"""
PLUTON V2 — Deterministic Semantic Plan Validator.
Enforces strict schema conformance, acyclic dependency graphs, parameter validity,
risk invariance, and anti-hallucination constraints on model-generated SemanticPlans.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from app.core.contracts import ExecutionContext
from .capability_schema import CapabilityRegistry
from .semantic_contracts import SemanticPlan, SemanticStep, TargetReferenceType


class SemanticValidationError(Exception):
    """Raised when a SemanticPlan violates deterministic validation rules."""
    pass


class SemanticPlanValidator:
    """Validates model-generated SemanticPlans deterministically before execution."""

    @classmethod
    def validate_plan(cls, plan: SemanticPlan, context: Optional[ExecutionContext] = None) -> list[str]:
        """Perform comprehensive deterministic validation, returning list of validation errors (empty if valid)."""
        errors: list[str] = []

        if not plan.goal and not plan.is_conversational:
            errors.append("MISSING_GOAL: SemanticPlan must declare a goal or be conversational.")

        if plan.is_conversational:
            if plan.steps:
                errors.append("INVALID_CONVERSATIONAL_STEPS: Conversational plans must have 0 executable steps.")
            return errors

        if not plan.steps:
            errors.append("EMPTY_PLAN: Operational SemanticPlan must contain at least 1 step.")
            return errors

        trusted_hwnds = set()
        if context:
            if context.bound_hwnd:
                trusted_hwnds.add(context.bound_hwnd)
            if context.workflow_context.active_hwnd:
                trusted_hwnds.add(context.workflow_context.active_hwnd)

        # 1. Step ID Uniqueness and Ordering
        seen_step_ids: set[int] = set()
        for idx, step in enumerate(plan.steps, start=1):
            if step.step_id in seen_step_ids:
                errors.append(f"DUPLICATE_STEP_ID: Step ID {step.step_id} is duplicated.")
            seen_step_ids.add(step.step_id)

            # 2. Capability Existence
            cap_contract = CapabilityRegistry.get_capability(step.capability)
            if not cap_contract:
                errors.append(f"UNKNOWN_CAPABILITY: Step {step.step_id} references unregistered capability '{step.capability}'.")
                continue

            # 3. Target vs Parameter Separation Check (Anti-Conflation)
            target_ref = step.target_reference
            raw_target = target_ref.raw_reference.strip().lower()

            prohibited_action_prefixes = ("calculate ", "compute ", "type ", "open ", "launch ", "click ", "press ", "navigate to ")
            if any(raw_target.startswith(p) for p in prohibited_action_prefixes):
                errors.append(f"ACTION_AS_TARGET: Step {step.step_id} has action phrase in target_reference: '{target_ref.raw_reference}'.")

            if re.search(r"\b\d+\s*[\*\+\/\^\=]\s*\d+\b", raw_target) and step.capability in ("app.launch", "browser.navigate"):
                errors.append(f"MATH_AS_TARGET: Step {step.step_id} has arithmetic expression in target_reference: '{target_ref.raw_reference}'.")

            # 4. Required Target Check
            if cap_contract.target_required:
                if target_ref.ref_type == TargetReferenceType.NONE and not target_ref.raw_reference:
                    errors.append(f"MISSING_REQUIRED_TARGET: Step {step.step_id} ({step.capability}) requires a target reference.")

            # 5. Anti-Hallucination: Reject Fabricated Physical Handles
            for k, v in step.parameters.items():
                if k in ("hwnd", "pointer", "handle") and isinstance(v, int) and v > 0:
                    if v not in trusted_hwnds:
                        errors.append(f"FABRICATED_PHYSICAL_ID: Step {step.step_id} attempted to supply synthetic '{k}={v}'.")

            # 6. Dependency Graph Validity
            for dep_id in step.dependencies:
                if dep_id >= step.step_id or dep_id not in seen_step_ids:
                    errors.append(f"INVALID_DEPENDENCY: Step {step.step_id} depends on forward or nonexistent step {dep_id}.")

            # 7. Verification Strategy Requirement
            if cap_contract.side_effect_level in ("MUTATING", "HIGH_RISK") and step.verification_strategy == "NONE":
                step.verification_strategy = cap_contract.default_verification

        # 8. Cycle Detection in Dependencies
        if cls._has_cycles(plan.steps):
            errors.append("CYCLIC_DEPENDENCIES: Step dependencies contain a cycle.")

        return errors

    @staticmethod
    def _has_cycles(steps: list[SemanticStep]) -> bool:
        """Check for cycles in step dependency DAG."""
        adj = {s.step_id: s.dependencies for s in steps}
        visited = {}

        def dfs(node: int) -> bool:
            if visited.get(node) == 1:
                return True
            if visited.get(node) == 2:
                return False
            visited[node] = 1
            for neighbor in adj.get(node, []):
                if dfs(neighbor):
                    return True
            visited[node] = 2
            return False

        for s in steps:
            if dfs(s.step_id):
                return True
        return False