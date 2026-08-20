"""
PLUTON V2 — Semantic Plan Normalizer.
Transforms validated SemanticPlans into Pluton canonical Plan, PlanStep, and Action contracts.
"""

from __future__ import annotations

import re
from typing import Any
from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TargetDomain,
    VerificationStrategy,
)
from .semantic_contracts import SemanticIntent, SemanticPlan, SemanticStep, TargetReferenceType


class SemanticPlanNormalizer:
    """Bridges SemanticPlan IR into Pluton runtime execution contracts."""

    @classmethod
    def normalize_to_canonical_plan(
        cls,
        semantic_plan: SemanticPlan,
        context: ExecutionContext,
    ) -> Plan:
        """Convert a SemanticPlan into a deterministic runtime Plan."""
        plan = Plan(task_id=context.task_id)

        if semantic_plan.is_conversational or not semantic_plan.steps:
            return plan

        current_domain = TargetDomain.APP

        for s in semantic_plan.steps:
            action, domain = cls._normalize_step(s, current_domain, context)
            if action:
                if domain:
                    current_domain = domain
                plan.steps.append(
                    PlanStep(
                        step_number=s.step_id,
                        description=s.rationale or f"{s.intent.value} on {s.target_reference.raw_reference or 'target'}",
                        action=action,
                        target_domain=domain,
                    )
                )

        return plan

    @classmethod
    def _normalize_step(
        cls,
        step: SemanticStep,
        active_domain: TargetDomain,
        context: ExecutionContext,
    ) -> tuple[Action, TargetDomain]:
        """Convert a single SemanticStep into a typed Action."""
        # 1. Map CapabilityType
        cap_val = step.capability
        try:
            capability = CapabilityType(cap_val)
        except ValueError:
            capability = CapabilityType.GENERAL_ACTION

        # 2. Map TargetDomain
        domain = TargetDomain.APP
        if capability in (CapabilityType.BROWSER_NAVIGATE, CapabilityType.BROWSER_SEARCH, CapabilityType.BROWSER_GET_TITLE):
            domain = TargetDomain.WEBPAGE
        elif capability in (CapabilityType.BROWSER_SWITCH_TAB, CapabilityType.BROWSER_CLOSE_TAB, CapabilityType.BROWSER_OPEN_TAB, CapabilityType.BROWSER_LIST_TABS, CapabilityType.BROWSER_RELOAD):
            domain = TargetDomain.TAB
        elif capability in (CapabilityType.FILESYSTEM_CREATE, CapabilityType.FILESYSTEM_READ, CapabilityType.FILESYSTEM_WRITE, CapabilityType.FILESYSTEM_DELETE, CapabilityType.FILESYSTEM_EXISTS, CapabilityType.FILESYSTEM_LIST):
            domain = TargetDomain.FILE
        elif capability in (CapabilityType.TERMINAL_EXECUTE, CapabilityType.TERMINAL_OUTPUT):
            domain = TargetDomain.TERMINAL
        elif capability in (CapabilityType.KEYBOARD_TYPE, CapabilityType.KEYBOARD_PRESS, CapabilityType.KEYBOARD_HOTKEY):
            domain = TargetDomain.KEYBOARD
        elif capability in (CapabilityType.WINDOW_LIST, CapabilityType.WINDOW_GET_STATE, CapabilityType.WINDOW_FOCUS, CapabilityType.WINDOW_MINIMIZE, CapabilityType.WINDOW_MAXIMIZE, CapabilityType.WINDOW_RESTORE, CapabilityType.WINDOW_CLOSE):
            domain = TargetDomain.WINDOW

        # 3. Resolve Target Reference for Action
        target_ref = step.target_reference
        target_str = target_ref.raw_reference.strip()

        # Handle contextual references
        if target_ref.ref_type == TargetReferenceType.CONTEXTUAL_ACTIVE_WINDOW:
            target_str = "active_window"
        elif target_ref.ref_type == TargetReferenceType.CONTEXTUAL_ACTIVE_BROWSER:
            target_str = context.active_browser or "browser"
        elif target_ref.ref_type == TargetReferenceType.CONTEXTUAL_ACTIVE_TAB:
            target_str = "active_tab"
        elif target_ref.ref_type == TargetReferenceType.CONTEXTUAL_LAST_FILE:
            target_str = context.metadata.get("last_file", target_str or "last_file")
        elif target_ref.ref_type == TargetReferenceType.CONTEXTUAL_PREVIOUS_TARGET:
            target_str = context.metadata.get("last_target", target_str or "target")

        # 4. Map Verification Strategy
        v_strat_str = (step.verification_strategy or "NONE").upper()
        try:
            v_strat = VerificationStrategy[v_strat_str]
        except KeyError:
            v_strat = VerificationStrategy.NONE

        # 5. Extract Execution Tier
        tier = ExecutionTier.TIER_1_NATIVE_API
        if capability in (CapabilityType.KEYBOARD_TYPE, CapabilityType.KEYBOARD_PRESS, CapabilityType.KEYBOARD_HOTKEY):
            tier = ExecutionTier.TIER_4_DETERMINISTIC_INPUT
        elif capability in (CapabilityType.UI_INVOKE, CapabilityType.MOUSE_CLICK):
            tier = ExecutionTier.TIER_3_UIA_AUTOMATION
        elif capability in (CapabilityType.WEB_CLICK, CapabilityType.WEB_TYPE):
            tier = ExecutionTier.TIER_2_APP_BROWSER_API

        # 6. Authoritative Safety Policy Enforcement (Runtime overrides model risk)
        from .capability_schema import CapabilityRegistry
        cap_contract = CapabilityRegistry.get(capability.value)
        final_risk = step.risk_level or "LOW"
        if cap_contract:
            if cap_contract.risk_level == "HIGH":
                final_risk = "HIGH"
            elif cap_contract.risk_level == "MEDIUM" and final_risk == "LOW":
                final_risk = "MEDIUM"

        # Parameters
        params = dict(step.parameters)
        if target_str and "target" not in params:
            params["target"] = target_str

        # Ensure text is in parameters for typing
        if capability == CapabilityType.KEYBOARD_TYPE and "text" not in params and "expression" in params:
            params["text"] = f"{params['expression']}="

        action = Action(
            capability=capability,
            target=target_str or "default",
            parameters=params,
            target_domain=domain,
            verification_strategy=v_strat,
            expected_state=step.expected_state,
            tier_requested=tier,
            risk_level=final_risk,
        )

        return action, domain