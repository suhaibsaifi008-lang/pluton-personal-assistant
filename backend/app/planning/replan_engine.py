"""
PLUTON V2 — Adaptive Dynamic Replan Engine
Diagnoses step failures, evaluates attempt budgets, invalidates stale state,
and generates materially different, permission-safe alternative actions.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import uuid4

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionTier,
    TargetDomain,
    VerificationStrategy,
)
from app.core.world_state import WorldState
from app.subsystems.computer.target_resolver import TARGET_RESOLVER
from app.subsystems.computer.target_resolver.contracts import TargetCandidate, TargetType
from .replan_contracts import FailureClassification, ReplanContext, ReplanDecision

logger = logging.getLogger("pluton.planning.replan_engine")


def classify_step_failure(
    action: Action,
    tool_status: str,
    tool_observed: dict[str, Any],
    verification_verified: bool,
    verification_message: str,
) -> tuple[FailureClassification, str]:
    """Classify execution or verification failure into authoritative taxonomy."""
    error_raw = str(tool_observed.get("error") or tool_observed.get("reason") or verification_message or "").strip()
    err_lower = error_raw.lower()

    if "ambiguous_target" in err_lower or "multiple matching" in err_lower:
        return FailureClassification.AMBIGUOUS_TARGET, error_raw or "AMBIGUOUS_TARGET"

    if "target_not_found" in err_lower or "not found" in err_lower or "could not resolve" in err_lower:
        return FailureClassification.TARGET_NOT_FOUND, error_raw or "TARGET_NOT_FOUND"

    if "permission" in err_lower or "denied" in err_lower or "unauthorized" in err_lower:
        return FailureClassification.PERMISSION_DENIED, error_raw or "PERMISSION_DENIED"

    if "stale" in err_lower or "dead" in err_lower or "iswindow" in err_lower or "invalid window" in err_lower:
        return FailureClassification.TARGET_STALE, error_raw or "TARGET_STALE"

    if "timeout" in err_lower or "timed out" in err_lower:
        return FailureClassification.TIMEOUT, error_raw or "TIMEOUT"

    if not verification_verified:
        if "postcondition" in err_lower or "presence" in err_lower or "absence" in err_lower or "match" in err_lower:
            return FailureClassification.POSTCONDITION_FAILED, verification_message or "POSTCONDITION_FAILED"
        return FailureClassification.VERIFICATION_FAILED, verification_message or "VERIFICATION_FAILED"

    if tool_status != "completed":
        return FailureClassification.EXECUTION_FAILED, error_raw or "EXECUTION_FAILED"

    return FailureClassification.EXECUTION_FAILED, error_raw or "Unknown step failure"


class ReplanEngine:
    """Adaptive dynamic replanning engine with strict budget enforcement and safety preservation."""

    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts

    def generate_replan(self, ctx: ReplanContext) -> ReplanDecision:
        """Produce an alternative plan/action within budget or declare unrecoverable failure."""
        # 1. HARD BUDGET LIMIT: Never exceed max_attempts
        if ctx.attempt_number >= ctx.max_attempts:
            logger.info("[REPLAN_ENGINE] Retry budget exhausted for step %s (%d/%d attempts)", ctx.step_number, ctx.attempt_number, ctx.max_attempts)
            return ReplanDecision(
                should_replan=False,
                selected_strategy="BUDGET_EXHAUSTED",
                reasoning=f"RETRY_BUDGET_EXHAUSTED: Reached maximum {ctx.max_attempts} attempts for step {ctx.step_number}.",
                attempt_count=ctx.attempt_number,
            )

        # 2. SAFETY & AMBIGUITY GATING: Never bypass safety refusals
        if ctx.failure_classification in (FailureClassification.AMBIGUOUS_TARGET, FailureClassification.PERMISSION_DENIED):
            logger.info("[REPLAN_ENGINE] Refusing replan for gated failure: %s", ctx.failure_classification.value)
            return ReplanDecision(
                should_replan=False,
                selected_strategy="REFUSE_GATED_FAILURE",
                reasoning=f"Gated failure cannot be automatically bypassed: {ctx.failure_diagnostic}",
                attempt_count=ctx.attempt_number,
            )

        # 3. IDEMPOTENCY / PARTIAL SUCCESS RECOVERY CHECK
        if ctx.world_state and self._check_already_satisfied(ctx):
            logger.info("[REPLAN_ENGINE] Step %s already physically satisfied in current WorldState (partial success).", ctx.step_number)
            return ReplanDecision(
                should_replan=True,
                selected_strategy="PARTIAL_SUCCESS_ADVANCE",
                new_action=None,  # Signal that no further execution is needed
                reasoning="Step postcondition already satisfied in refreshed WorldState.",
                attempt_count=ctx.attempt_number + 1,
            )

        # 4. GENERATE MATERIALLY DIFFERENT STRATEGY BASED ON DOMAIN & FAILURE
        action = ctx.original_action
        cap = action.capability
        params = dict(action.parameters)
        invalidated: list[str] = list(ctx.invalidated_targets)

        # A. Browser Navigation & Tab Failures
        if cap in (CapabilityType.BROWSER_NAVIGATE, CapabilityType.BROWSER_SWITCH_TAB, CapabilityType.BROWSER_OPEN_TAB):
            strategy_name = "browser_fresh_tab"
            if strategy_name not in ctx.prior_strategies:
                logger.info("[REPLAN_ENGINE] Selecting alternative strategy: %s for step %s", strategy_name, ctx.step_number)
                new_params = dict(params)
                new_params["force_new_tab"] = True
                new_params["reuse_existing"] = False
                new_action = Action(
                    capability=CapabilityType.BROWSER_NAVIGATE,
                    target=action.target,
                    parameters=new_params,
                    target_domain=TargetDomain.WEBPAGE,
                    verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE,
                    expected_state=action.expected_state,
                    tier_requested=action.tier_requested,
                    risk_level=action.risk_level,
                )
                return ReplanDecision(
                    should_replan=True,
                    selected_strategy=strategy_name,
                    new_action=new_action,
                    reasoning="Switched from existing tab reuse to fresh tab navigation.",
                    invalidated_targets=invalidated,
                    attempt_count=ctx.attempt_number + 1,
                )

            # Attempt 3 for browser: Alternate browser or direct URL launch via OS shell
            strategy_name_3 = "browser_system_launch"
            if strategy_name_3 not in ctx.prior_strategies:
                new_action = Action(
                    capability=CapabilityType.BROWSER_NAVIGATE,
                    target=action.target,
                    parameters={"url": action.target, "browser": "Brave", "direct_shell": True},
                    target_domain=TargetDomain.WEBPAGE,
                    verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE,
                    expected_state=action.expected_state,
                    tier_requested=action.tier_requested,
                    risk_level=action.risk_level,
                )
                return ReplanDecision(
                    should_replan=True,
                    selected_strategy=strategy_name_3,
                    new_action=new_action,
                    reasoning="Fallback to direct system browser launch.",
                    invalidated_targets=invalidated,
                    attempt_count=ctx.attempt_number + 1,
                )

        # B. Window Focus / Stale HWND / App Launch Failures
        elif cap in (CapabilityType.WINDOW_FOCUS, CapabilityType.APP_LAUNCH, CapabilityType.APP_FOCUS):
            if ctx.execution_context and ctx.execution_context.bound_hwnd:
                invalidated.append(f"hwnd:{ctx.execution_context.bound_hwnd}")
                ctx.execution_context.workflow_context.invalidate_window()

            strategy_name = "app_relaunch_or_rediscover"
            if strategy_name not in ctx.prior_strategies:
                logger.info("[REPLAN_ENGINE] Selecting alternative strategy: %s for step %s", strategy_name, ctx.step_number)
                new_params = dict(params)
                new_params.pop("hwnd", None)
                new_params["force_launch"] = True
                new_action = Action(
                    capability=CapabilityType.APP_LAUNCH,
                    target=action.target,
                    parameters=new_params,
                    target_domain=TargetDomain.APP,
                    verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                    expected_state=action.expected_state or action.target,
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    risk_level=action.risk_level,
                )
                return ReplanDecision(
                    should_replan=True,
                    selected_strategy=strategy_name,
                    new_action=new_action,
                    reasoning="Invalidated stale window handle and re-launching target application cleanly.",
                    invalidated_targets=invalidated,
                    attempt_count=ctx.attempt_number + 1,
                )

            strategy_name_win3 = "app_fallback_native_start"
            if strategy_name_win3 not in ctx.prior_strategies:
                new_action = Action(
                    capability=CapabilityType.APP_LAUNCH,
                    target=action.target,
                    parameters={"app_name": action.target, "use_shell": True},
                    target_domain=TargetDomain.APP,
                    verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                    expected_state=action.expected_state or action.target,
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    risk_level=action.risk_level,
                )
                return ReplanDecision(
                    should_replan=True,
                    selected_strategy=strategy_name_win3,
                    new_action=new_action,
                    reasoning="Fallback to native system shell launch.",
                    invalidated_targets=invalidated,
                    attempt_count=ctx.attempt_number + 1,
                )

        # C. UI Interaction / Click / Type / Invoke Failures
        elif cap in (CapabilityType.UI_INVOKE, CapabilityType.KEYBOARD_TYPE, CapabilityType.MOUSE_CLICK):
            strategy_name = "ui_fallback_input_tier"
            if strategy_name not in ctx.prior_strategies:
                logger.info("[REPLAN_ENGINE] Selecting alternative strategy: %s for step %s", strategy_name, ctx.step_number)
                # Escalate tier or switch input modality
                new_tier = ExecutionTier.TIER_4_DETERMINISTIC_INPUT if action.tier_requested == ExecutionTier.TIER_1_NATIVE_API else ExecutionTier.TIER_3_UIA_AUTOMATION
                new_action = Action(
                    capability=action.capability,
                    target=action.target,
                    parameters=dict(params),
                    target_domain=action.target_domain,
                    verification_strategy=action.verification_strategy,
                    expected_state=action.expected_state,
                    tier_requested=new_tier,
                    risk_level=action.risk_level,
                )
                return ReplanDecision(
                    should_replan=True,
                    selected_strategy=strategy_name,
                    new_action=new_action,
                    reasoning="Escalated execution tier for input interaction.",
                    invalidated_targets=invalidated,
                    attempt_count=ctx.attempt_number + 1,
                )

        # D. Generic Discovery Candidate Fallback
        if ctx.remaining_candidates:
            alt_cand = ctx.remaining_candidates[0]
            strategy_name = f"candidate_fallback_{alt_cand.source}"
            if strategy_name not in ctx.prior_strategies:
                new_action = Action(
                    capability=CapabilityType.BROWSER_NAVIGATE if alt_cand.target_type in (TargetType.LOCAL_WEB_SERVICE, TargetType.PUBLIC_WEB_DOMAIN) else CapabilityType.APP_LAUNCH,
                    target=alt_cand.identity,
                    parameters={"url": alt_cand.identity} if alt_cand.target_type in (TargetType.LOCAL_WEB_SERVICE, TargetType.PUBLIC_WEB_DOMAIN) else {"exe": alt_cand.identity},
                    target_domain=TargetDomain.WEBPAGE if alt_cand.target_type in (TargetType.LOCAL_WEB_SERVICE, TargetType.PUBLIC_WEB_DOMAIN) else TargetDomain.APP,
                    verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE if alt_cand.target_type in (TargetType.LOCAL_WEB_SERVICE, TargetType.PUBLIC_WEB_DOMAIN) else VerificationStrategy.WINDOW_PRESENCE,
                    expected_state=alt_cand.name,
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    risk_level=action.risk_level,
                )
                return ReplanDecision(
                    should_replan=True,
                    selected_strategy=strategy_name,
                    new_action=new_action,
                    reasoning=f"Selected alternate discovered candidate: {alt_cand.name} ({alt_cand.identity})",
                    invalidated_targets=invalidated,
                    attempt_count=ctx.attempt_number + 1,
                )

        # If no materially different strategy is available
        return ReplanDecision(
            should_replan=False,
            selected_strategy="NO_ALTERNATIVE_STRATEGY",
            reasoning=f"No alternative valid recovery strategy available for capability '{cap.value}'.",
            attempt_count=ctx.attempt_number,
        )

    def _check_already_satisfied(self, ctx: ReplanContext) -> bool:
        """Evaluate if the step's expected outcome was already physically achieved (partial success)."""
        if not ctx.world_state:
            return False

        action = ctx.original_action
        v_strat = action.verification_strategy
        exp = action.expected_state

        if v_strat == VerificationStrategy.WINDOW_PRESENCE and exp:
            exp_str = str(exp).lower()
            return any(exp_str in w.title.lower() for w in ctx.world_state.visible_windows)

        if v_strat == VerificationStrategy.BROWSER_TAB_PRESENCE and exp:
            exp_str = str(exp).lower()
            if ctx.world_state.browser_session:
                return exp_str in ctx.world_state.browser_session.active_title.lower() or exp_str in ctx.world_state.browser_session.active_url.lower()

        return False


REPLAN_ENGINE = ReplanEngine()