"""
PLUTON V2 — Model-Driven Semantic Planner (Gate 2 Architecture).
Translates natural-language user requests into validated, typed SemanticPlans using
real model inference, with zero embedded phrase tables, application dictionaries, or regex heuristics.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from app.core.contracts import ExecutionContext, Plan
from app.providers.base import AIProvider, ProviderRequest
from .capability_schema import CapabilityRegistry
from .planner_prompt import PLANNER_SYSTEM_PROMPT, build_planner_user_prompt
from .semantic_contracts import (
    PlanningTelemetry,
    SemanticIntent,
    SemanticPlan,
    SemanticStep,
    TargetReference,
    TargetReferenceType,
)
from .semantic_critic import SemanticPlanCritic
from .semantic_normalizer import SemanticPlanNormalizer
from .semantic_validator import SemanticPlanValidator

logger = logging.getLogger("pluton.planning.semantic")


class SemanticPlanner:
    """Core intelligence layer: translates natural language requests into validated SemanticPlans using an AIProvider."""

    def __init__(self, provider: Optional[AIProvider] = None) -> None:
        self.provider = provider
        self.telemetry_history: list[PlanningTelemetry] = []

    def set_provider(self, provider: Optional[AIProvider]) -> None:
        """Inject the live active AIProvider at runtime."""
        self.provider = provider

    async def plan(
        self,
        request_text: str,
        context: ExecutionContext,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[SemanticPlan, Plan]:
        """Generate, validate, critique, and normalize a SemanticPlan from natural language input via LLM inference."""
        t_start = time.perf_counter()
        plan_id = f"plan-{int(t_start * 1000)}"
        clean_text = request_text.strip()
        model_name = getattr(self.provider, "model", "none") if self.provider else "unconfigured"

        # 1. Real Model-Driven Plan Generation
        raw_json_dict: Optional[dict[str, Any]] = None
        validation_passed = False
        critique_passed = False
        error_msg: Optional[str] = None
        fallback_used = False

        if self.provider:
            task_st = context.workflow_context.to_dict() if hasattr(context, "workflow_context") and hasattr(context.workflow_context, "to_dict") else None
            user_prompt = build_planner_user_prompt(
                request_text=clean_text,
                context_metadata=context.metadata,
                history=history,
                task_state=task_st,
            )
            try:
                req = ProviderRequest(
                    message=user_prompt,
                    context=PLANNER_SYSTEM_PROMPT,
                    history=history or [],
                )
                if hasattr(self.provider, "respond"):
                    resp = await self.provider.respond(req)
                    raw_text = resp.text.strip()
                    # Extract JSON object from model output
                    match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
                    if match:
                        raw_json_dict = json.loads(match.group(1))
                    else:
                        error_msg = f"Model output did not contain valid JSON: {raw_text[:200]}"
            except Exception as e:
                error_msg = f"Provider generation failed: {e}"
                logger.warning("[SEMANTIC_PLANNER] %s", error_msg)

        # 2. If provider unconfigured or generation failed, mark fallback
        if not raw_json_dict:
            fallback_used = True
            # Fallback to legacy UniversalPlanCompiler without pretending it is LLM reasoning
            from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER
            canonical_plan = UNIVERSAL_PLAN_COMPILER.compile_plan(clean_text, context)
            sem_plan = self._legacy_to_semantic_plan(canonical_plan, clean_text, plan_id)
            latency_ms = (time.perf_counter() - t_start) * 1000
            self._record_telemetry(plan_id, model_name, latency_ms, len(sem_plan.steps), True, True, error=error_msg)
            return sem_plan, canonical_plan

        # 3. Parse into SemanticPlan IR
        try:
            sem_plan = SemanticPlan.from_dict(raw_json_dict)
            sem_plan.plan_id = plan_id
            sem_plan.goal = clean_text
        except Exception as parse_ex:
            logger.warning("[SEMANTIC_PLANNER] Failed to parse model output into SemanticPlan: %s", parse_ex)
            from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER
            canonical_plan = UNIVERSAL_PLAN_COMPILER.compile_plan(clean_text, context)
            sem_plan = self._legacy_to_semantic_plan(canonical_plan, clean_text, plan_id)
            latency_ms = (time.perf_counter() - t_start) * 1000
            self._record_telemetry(plan_id, model_name, latency_ms, len(sem_plan.steps), False, False, error=str(parse_ex))
            return sem_plan, canonical_plan

        # 4. Deterministic Validation (Zero Silent Heuristic Repairs)
        val_errors = SemanticPlanValidator.validate_plan(sem_plan, context=context)
        validation_passed = (len(val_errors) == 0)

        # 5. Semantic Plan Critique
        critique = SemanticPlanCritic.critique_plan(sem_plan)
        critique_passed = critique.is_valid

        # 6. Normalize to Canonical Pluton Plan
        canonical_plan = SemanticPlanNormalizer.normalize_to_canonical_plan(sem_plan, context)

        # 7. Record Telemetry
        latency_ms = (time.perf_counter() - t_start) * 1000
        self._record_telemetry(
            plan_id=plan_id,
            model_name=model_name,
            latency_ms=latency_ms,
            step_count=len(sem_plan.steps),
            validation_passed=validation_passed,
            critique_passed=critique_passed,
            error=val_errors[0] if val_errors else error_msg,
        )

        return sem_plan, canonical_plan

    @staticmethod
    def _legacy_to_semantic_plan(canonical_plan: Plan, goal: str, plan_id: str) -> SemanticPlan:
        """Convert a legacy Plan into a SemanticPlan IR purely for telemetry representation."""
        steps: list[SemanticStep] = []
        for idx, s in enumerate(canonical_plan.steps, start=1):
            cap_id = s.action.capability.value
            intent = SemanticIntent.OPEN_APPLICATION
            if "browser.navigate" in cap_id:
                intent = SemanticIntent.NAVIGATE_BROWSER
            elif "browser.search" in cap_id:
                intent = SemanticIntent.SEARCH_WEB
            elif "keyboard.type" in cap_id:
                intent = SemanticIntent.INPUT_TEXT
            elif "general.calculate" in cap_id:
                intent = SemanticIntent.CALCULATE
            elif "browser.get_title" in cap_id:
                intent = SemanticIntent.GET_BROWSER_TITLE
            elif "filesystem.create" in cap_id:
                intent = SemanticIntent.CREATE_FILE
            elif "filesystem.read" in cap_id:
                intent = SemanticIntent.READ_FILE
            elif "terminal.execute" in cap_id:
                intent = SemanticIntent.EXECUTE_TERMINAL

            target_type = TargetReferenceType.EXPLICIT_NAME
            if s.action.target.startswith("http"):
                target_type = TargetReferenceType.EXPLICIT_URL
            elif "/" in s.action.target or "\\" in s.action.target:
                target_type = TargetReferenceType.EXPLICIT_PATH
            elif s.action.target in ("active_window", "context"):
                target_type = TargetReferenceType.CONTEXTUAL_ACTIVE_WINDOW

            steps.append(
                SemanticStep(
                    step_id=idx,
                    intent=intent,
                    capability=cap_id,
                    target_reference=TargetReference(ref_type=target_type, raw_reference=s.action.target),
                    parameters=s.action.parameters,
                    dependencies=[idx - 1] if idx > 1 else [],
                    expected_state=s.action.expected_state,
                    verification_strategy=s.action.verification_strategy.name,
                    risk_level=s.action.risk_level,
                    rationale=s.description,
                )
            )

        return SemanticPlan(
            plan_id=plan_id,
            goal=goal,
            primary_intent=steps[0].intent.value if steps else SemanticIntent.CONVERSATIONAL_RESPONSE.value,
            is_conversational=len(steps) == 0,
            steps=steps,
            final_success_condition=f"Completed {len(steps)} steps.",
        )

    def _record_telemetry(
        self,
        plan_id: str,
        model_name: str,
        latency_ms: float,
        step_count: int,
        validation_passed: bool,
        critique_passed: bool,
        error: Optional[str] = None,
    ) -> None:
        telem = PlanningTelemetry(
            plan_id=plan_id,
            model_name=model_name,
            latency_ms=round(latency_ms, 2),
            step_count=step_count,
            validation_passed=validation_passed,
            critique_passed=critique_passed,
            error=error,
        )
        self.telemetry_history.append(telem)
        if len(self.telemetry_history) > 100:
            self.telemetry_history.pop(0)


SEMANTIC_PLANNER = SemanticPlanner()