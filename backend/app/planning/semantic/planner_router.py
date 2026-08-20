"""
PLUTON V2 — Planner Router (Gate 2 Shadow Mode).
Routes planning requests in SHADOW mode: compiles authoritative known-good plan for execution
while asynchronously evaluating the model-driven Semantic Planner in the background.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Optional
from app.core.contracts import ExecutionContext, Plan
from .semantic_contracts import SemanticPlan
from .semantic_planner import SEMANTIC_PLANNER, SemanticPlanner

logger = logging.getLogger("pluton.planning.router")


@dataclass
class ShadowEvaluationRecord:
    """Telemetry record comparing authoritative legacy plan vs model-driven semantic plan."""
    request_text: str
    legacy_step_count: int
    semantic_step_count: int
    semantic_validation_passed: bool
    semantic_critique_passed: bool
    intent_agreement: bool
    target_agreement: bool
    latency_ms: float
    model_name: str
    evaluated_at: float = field(default_factory=time.time)


class PlannerRouter:
    """Routes planning requests and coordinates shadow evaluation without risking execution."""

    def __init__(self, mode: str = "shadow") -> None:
        self.mode = mode  # "shadow" (default), "semantic", "deterministic"
        self.semantic_planner = SEMANTIC_PLANNER
        self.shadow_history: list[ShadowEvaluationRecord] = []

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    async def async_plan_request(
        self,
        request_text: str,
        context: ExecutionContext,
        history: list[dict[str, str]] | None = None,
    ) -> Plan:
        """Asynchronously execute plan generation with zero thread pool overhead."""
        from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER

        legacy_plan = UNIVERSAL_PLAN_COMPILER.compile_plan(request_text, context)
        if self.mode == "deterministic":
            return legacy_plan

        t_start = time.perf_counter()
        try:
            sem_plan, canonical_sem = await self.semantic_planner.plan(request_text, context, history)
            self._evaluate_shadow(request_text, legacy_plan, sem_plan, (time.perf_counter() - t_start) * 1000)
            if self.mode == "semantic":
                return canonical_sem
        except Exception as ex:
            logger.warning("[PLANNER_ROUTER] Async shadow semantic evaluation exception: %s", ex)

        return legacy_plan

    def plan_request(self, request_text: str, context: ExecutionContext) -> Plan:
        """Execute plan generation according to active router mode (synchronous wrapper)."""
        from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER

        legacy_plan = UNIVERSAL_PLAN_COMPILER.compile_plan(request_text, context)
        if self.mode == "deterministic":
            return legacy_plan

        t_start = time.perf_counter()
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Launch shadow background evaluation asynchronously without blocking execution
                asyncio.create_task(self._shadow_background_eval(request_text, context, legacy_plan, t_start))
            else:
                sem_plan, canonical_sem = asyncio.run(
                    self.semantic_planner.plan(request_text, context)
                )
                self._evaluate_shadow(request_text, legacy_plan, sem_plan, (time.perf_counter() - t_start) * 1000)
                if self.mode == "semantic":
                    return canonical_sem

        except Exception as ex:
            logger.warning("[PLANNER_ROUTER] Shadow semantic evaluation exception: %s", ex)

        return legacy_plan

    async def _shadow_background_eval(self, request_text: str, context: ExecutionContext, legacy_plan: Plan, t_start: float) -> None:
        """Execute background shadow evaluation without adding latency to caller."""
        try:
            sem_plan, _ = await self.semantic_planner.plan(request_text, context)
            self._evaluate_shadow(request_text, legacy_plan, sem_plan, (time.perf_counter() - t_start) * 1000)
        except Exception as ex:
            logger.warning("[PLANNER_ROUTER] Background shadow evaluation failed: %s", ex)

    def _evaluate_shadow(
        self,
        request_text: str,
        legacy_plan: Plan,
        sem_plan: SemanticPlan,
        latency_ms: float,
    ) -> None:
        """Compare legacy and semantic plans across intent, target, and step structure."""
        legacy_steps = legacy_plan.steps
        sem_steps = sem_plan.steps

        # Intent agreement: Both agree on conversational vs operational
        is_legacy_conv = (len(legacy_steps) == 0)
        intent_agree = (is_legacy_conv == sem_plan.is_conversational)

        # Target agreement: Top target match (if operational)
        target_agree = True
        if not is_legacy_conv and legacy_steps and sem_steps:
            leg_target = str(legacy_steps[0].action.target or "").lower()
            sem_target = str(sem_steps[0].target_reference.raw_reference or "").lower()
            target_agree = (leg_target in sem_target or sem_target in leg_target)

        record = ShadowEvaluationRecord(
            request_text=request_text,
            legacy_step_count=len(legacy_steps),
            semantic_step_count=len(sem_steps),
            semantic_validation_passed=bool(sem_plan.steps or sem_plan.is_conversational),
            semantic_critique_passed=True,
            intent_agreement=intent_agree,
            target_agreement=target_agree,
            latency_ms=round(latency_ms, 2),
            model_name=getattr(self.semantic_planner.provider, "model", "none") if self.semantic_planner.provider else "unconfigured",
        )
        self.shadow_history.append(record)
        if len(self.shadow_history) > 200:
            self.shadow_history.pop(0)


PLANNER_ROUTER = PlannerRouter(mode="shadow")