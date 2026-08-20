"""
PLUTON V2 — Adaptive Dynamic Replanning Data Contracts
Defines failure classifications, replanning contexts, and replan decision models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.core.contracts import Action, ExecutionContext, PlanStep
from app.core.world_state import WorldState
from app.subsystems.computer.target_resolver.contracts import TargetCandidate


class FailureClassification(str, Enum):
    """Authoritative failure taxonomy for execution and verification failures."""
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    TARGET_STALE = "TARGET_STALE"
    TARGET_OFFLINE = "TARGET_OFFLINE"
    TARGET_BLOCKED = "TARGET_BLOCKED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TIMEOUT = "TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    ENVIRONMENT_CHANGED = "ENVIRONMENT_CHANGED"


@dataclass
class ReplanContext:
    """Structured context passed to the replanning engine upon step verification/execution failure."""
    task_id: str
    step_number: int
    original_action: Action
    attempt_number: int
    max_attempts: int = 3
    failure_classification: FailureClassification = FailureClassification.EXECUTION_FAILED
    failure_diagnostic: str = ""
    prior_strategies: list[str] = field(default_factory=list)
    world_state: Optional[WorldState] = None
    world_state_delta: dict[str, Any] = field(default_factory=dict)
    invalidated_targets: list[str] = field(default_factory=list)
    remaining_candidates: list[TargetCandidate] = field(default_factory=list)
    execution_context: Optional[ExecutionContext] = None


@dataclass
class ReplanDecision:
    """Authoritative decision produced by the replanning engine."""
    should_replan: bool
    selected_strategy: str
    new_action: Optional[Action] = None
    reasoning: str = ""
    invalidated_targets: list[str] = field(default_factory=list)
    attempt_count: int = 1