"""
PLUTON V2 — Semantic Plan Critic.
Performs deterministic critique on generated plans: checks goal satisfaction,
detects redundant side-effects, and confirms complete multi-step coverage.
"""

from __future__ import annotations

from .semantic_contracts import SemanticIntent, SemanticPlan, SemanticPlanCritique


class SemanticPlanCritic:
    """Evaluates whether a SemanticPlan genuinely satisfies the user's intent and safety boundaries."""

    @classmethod
    def critique_plan(cls, plan: SemanticPlan) -> SemanticPlanCritique:
        """Critique the plan for completeness, efficiency, and goal satisfaction."""
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        if plan.is_conversational:
            return SemanticPlanCritique(is_valid=True, issues=[], suggestions=[], score=1.0)

        # 1. Goal vs Step Alignment
        goal_lower = plan.goal.lower()
        step_intents = [s.intent for s in plan.steps]

        # Check: If goal asked to open something and calculate, did we produce both?
        if any(w in goal_lower for w in ("calculate", "work out", "compute", "multiplied", "times", "plus", "divided")):
            if SemanticIntent.INPUT_TEXT not in step_intents and SemanticIntent.CALCULATE not in step_intents:
                issues.append("MISSING_CALCULATION_STEP: Request asked for calculation but plan lacks input/calculation step.")
                score -= 0.3

        # Check: If goal asked to verify navigation/page load, is there verification?
        if any(w in goal_lower for w in ("verify", "make sure", "confirm", "check that")):
            has_verification = any(s.verification_strategy != "NONE" or s.intent in (SemanticIntent.GET_BROWSER_TITLE, SemanticIntent.GET_WINDOW_STATE, SemanticIntent.READ_FILE) for s in plan.steps)
            if not has_verification:
                issues.append("MISSING_EXPLICIT_VERIFICATION: User requested explicit verification but no verification step was configured.")
                score -= 0.2

        # 2. Redundant Duplicate Steps Detection
        seen_actions = set()
        for s in plan.steps:
            act_sig = (s.capability, s.target_reference.raw_reference, str(s.parameters))
            if act_sig in seen_actions and s.capability not in ("keyboard.type", "keyboard.press"):
                suggestions.append(f"POTENTIAL_DUPLICATE: Step {s.step_id} repeats identical action {s.capability}.")
                score -= 0.1
            seen_actions.add(act_sig)

        is_valid = len(issues) == 0
        return SemanticPlanCritique(
            is_valid=is_valid,
            issues=issues,
            suggestions=suggestions,
            score=max(0.0, score),
        )