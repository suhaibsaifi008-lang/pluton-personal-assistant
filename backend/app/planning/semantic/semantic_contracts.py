"""
PLUTON V2 — Semantic Planner Intermediate Representation (IR) Contracts.
Strongly typed data contracts for semantic plans, steps, intents, target references, and validation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Any, Optional
import uuid


class SemanticIntent(str, Enum):
    """High-level semantic intent category independent of model or specific phrasing."""
    OPEN_APPLICATION = "open_application"
    NAVIGATE_BROWSER = "navigate_browser"
    SEARCH_WEB = "search_web"
    CALCULATE = "calculate"
    INPUT_TEXT = "input_text"
    CLICK_ELEMENT = "click_element"
    SELECT_OPTION = "select_option"
    TOGGLE_ELEMENT = "toggle_element"
    CREATE_FILE = "create_file"
    READ_FILE = "read_file"
    EXECUTE_TERMINAL = "execute_terminal"
    GET_WINDOW_STATE = "get_window_state"
    GET_BROWSER_TITLE = "get_browser_title"
    LIST_WINDOWS = "list_windows"
    LIST_TABS = "list_tabs"
    CLOSE_WINDOW = "close_window"
    CLOSE_TAB = "close_tab"
    SWITCH_TAB = "switch_tab"
    HOTKEY = "hotkey"
    DRAG_DROP = "drag_drop"
    CONVERSATIONAL_RESPONSE = "conversational_response"
    CLARIFICATION_REQUIRED = "clarification_required"


class TargetReferenceType(str, Enum):
    """Classification of how a target entity is referenced."""
    EXPLICIT_NAME = "explicit_name"          # e.g., "Calculator", "Notepad", "Spotify"
    EXPLICIT_URL = "explicit_url"            # e.g., "https://example.com", "http://127.0.0.1:5173"
    EXPLICIT_PATH = "explicit_path"          # e.g., "Downloads/report.txt"
    CONTEXTUAL_ACTIVE_WINDOW = "contextual_active_window"  # e.g., "the active window", "current app"
    CONTEXTUAL_ACTIVE_BROWSER = "contextual_active_browser"# e.g., "my browser", "the open browser"
    CONTEXTUAL_ACTIVE_TAB = "contextual_active_tab"        # e.g., "the current tab"
    CONTEXTUAL_PREVIOUS_TARGET = "contextual_previous_target" # e.g., "it", "that", "the window opened in step 1"
    CONTEXTUAL_PREVIOUS_STEP_RESULT = "contextual_previous_step_result" # e.g., "the calculated result", "previous output"
    CONTEXTUAL_LAST_FILE = "contextual_last_file"          # e.g., "the file I created earlier"
    CONTEXTUAL_APPLICATION_REUSE = "contextual_application_reuse" # e.g., "use the existing open app/tab"
    NONE = "none"                            # No target required (e.g. calculation, listing, terminal command)


@dataclass
class SemanticGoal:
    """Canonical representation of the user's high-level desired outcome and constraints."""
    objective: str = ""                         # e.g., "open_application", "navigate_browser", "calculate", "close_tab", "verify_state"
    target_concept: TargetReference = field(default_factory=lambda: TargetReference(TargetReferenceType.NONE))
    parameters: dict[str, Any] = field(default_factory=dict)
    success_criteria: str = ""
    context_requirements: list[str] = field(default_factory=list) # e.g. ["browser_context", "active_window", "file_system"]
    is_conversational: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "target_concept": self.target_concept.to_dict(),
            "parameters": self.parameters,
            "success_criteria": self.success_criteria,
            "context_requirements": self.context_requirements,
            "is_conversational": self.is_conversational,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticGoal:
        target_ref_data = data.get("target_concept", {})
        if isinstance(target_ref_data, dict):
            target_ref = TargetReference.from_dict(target_ref_data)
        elif isinstance(target_ref_data, str) and target_ref_data:
            target_ref = TargetReference(TargetReferenceType.EXPLICIT_NAME, raw_reference=target_ref_data)
        else:
            target_ref = TargetReference(TargetReferenceType.NONE)

        return cls(
            objective=data.get("objective", ""),
            target_concept=target_ref,
            parameters=data.get("parameters", {}) or {},
            success_criteria=data.get("success_criteria", ""),
            context_requirements=data.get("context_requirements", []) or [],
            is_conversational=bool(data.get("is_conversational", False)),
            rationale=data.get("rationale", ""),
        )


@dataclass
class TargetReference:
    """Disambiguated target reference metadata separating the target entity from action data."""
    ref_type: TargetReferenceType
    raw_reference: str = ""
    context_key: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_type": self.ref_type.value,
            "raw_reference": self.raw_reference,
            "context_key": self.context_key,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetReference:
        ref_type_str = data.get("ref_type", TargetReferenceType.NONE.value)
        try:
            ref_type = TargetReferenceType(ref_type_str)
        except ValueError:
            ref_type = TargetReferenceType.EXPLICIT_NAME if data.get("raw_reference") else TargetReferenceType.NONE
        return cls(
            ref_type=ref_type,
            raw_reference=data.get("raw_reference", ""),
            context_key=data.get("context_key"),
            description=data.get("description", ""),
        )


@dataclass
class SemanticStep:
    """Individual typed semantic action step within a SemanticPlan."""
    step_id: int
    intent: SemanticIntent
    capability: str
    target_reference: TargetReference
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: list[int] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    expected_state: Optional[str] = None
    verification_strategy: str = "NONE"
    risk_level: str = "LOW"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "intent": self.intent.value,
            "capability": self.capability,
            "target_reference": self.target_reference.to_dict(),
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "preconditions": self.preconditions,
            "expected_state": self.expected_state,
            "verification_strategy": self.verification_strategy,
            "risk_level": self.risk_level,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticStep:
        capability = str(data.get("capability", "general.action")).strip()
        from .capability_schema import CapabilityRegistry
        contract = CapabilityRegistry.get(capability)

        intent_str = data.get("intent", SemanticIntent.CONVERSATIONAL_RESPONSE.value)
        try:
            intent = SemanticIntent(intent_str)
        except ValueError:
            intent = SemanticIntent.CONVERSATIONAL_RESPONSE

        # Canonical Intent Alignment: if capability has a designated semantic intent, align it
        if contract and (intent == SemanticIntent.CONVERSATIONAL_RESPONSE or not intent_str):
            try:
                intent = SemanticIntent(contract.semantic_intent)
            except ValueError:
                pass

        target_ref_data = data.get("target_reference")
        if isinstance(target_ref_data, dict):
            target_ref = TargetReference.from_dict(target_ref_data)
        elif isinstance(target_ref_data, str) and target_ref_data:
            target_ref = TargetReference(ref_type=TargetReferenceType.EXPLICIT_NAME, raw_reference=target_ref_data)
        else:
            target_ref = TargetReference(ref_type=TargetReferenceType.NONE)

        parameters = data.get("parameters", {}) or {}

        # Generic Contract-Driven Target Promotion: If capability requires target and target_reference is empty
        if contract and contract.target_required and (not target_ref.raw_reference or target_ref.ref_type == TargetReferenceType.NONE):
            for candidate_key in ("target", "app_name", "url", "path", "window_title", "command", "query", "app", "window"):
                if candidate_key in parameters and str(parameters[candidate_key]).strip():
                    target_ref.raw_reference = str(parameters[candidate_key]).strip()
                    allowed = contract.allowed_target_types
                    target_ref.ref_type = TargetReferenceType(allowed[0]) if allowed else TargetReferenceType.EXPLICIT_NAME
                    break

        def _parse_id(val: Any, default: int = 1) -> int:
            if isinstance(val, int):
                return val
            digits = re.findall(r"\d+", str(val or ""))
            return int(digits[0]) if digits else default

        # Authoritative Risk Enforcement: runtime truth wins
        model_risk = str(data.get("risk_level", "LOW")).upper()
        if contract and contract.risk_level == "HIGH":
            risk_level = "HIGH"
        else:
            risk_level = model_risk if model_risk in ("LOW", "MEDIUM", "HIGH") else (contract.risk_level if contract else "LOW")

        return cls(
            step_id=_parse_id(data.get("step_id"), 1),
            intent=intent,
            capability=capability,
            target_reference=target_ref,
            parameters=parameters,
            dependencies=[_parse_id(d, 1) for d in data.get("dependencies", [])],
            preconditions=data.get("preconditions", []) or [],
            expected_state=data.get("expected_state"),
            verification_strategy=data.get("verification_strategy") or (contract.default_verification if contract else "NONE"),
            risk_level=risk_level,
            rationale=data.get("rationale", ""),
        )


@dataclass
class SemanticPlan:
    """Canonical Intermediate Representation (IR) of a user request's semantic execution plan."""
    plan_id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    goal: str = ""
    semantic_goal: Optional[SemanticGoal] = None
    primary_intent: str = ""
    is_conversational: bool = False
    assumptions: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    steps: list[SemanticStep] = field(default_factory=list)
    final_success_condition: str = ""
    risk_level: str = "LOW"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "semantic_goal": self.semantic_goal.to_dict() if self.semantic_goal else None,
            "primary_intent": self.primary_intent,
            "is_conversational": self.is_conversational,
            "assumptions": self.assumptions,
            "entities": self.entities,
            "steps": [s.to_dict() for s in self.steps],
            "final_success_condition": self.final_success_condition,
            "risk_level": self.risk_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticPlan:
        steps_raw = data.get("steps", [])
        steps = [SemanticStep.from_dict(s) for s in steps_raw if isinstance(s, dict)]
        
        # Deterministic Step ID Re-indexing (eliminate duplicate step ID errors)
        step_ids = [s.step_id for s in steps]
        if len(step_ids) != len(set(step_ids)):
            for idx, s in enumerate(steps, start=1):
                s.step_id = idx

        is_conv = bool(data.get("is_conversational", False))
        if steps and is_conv:
            is_conv = False

        primary_intent = data.get("primary_intent", "")
        if steps and (not primary_intent or primary_intent == SemanticIntent.CONVERSATIONAL_RESPONSE.value):
            primary_intent = steps[0].intent.value

        goal_data = data.get("semantic_goal")
        sem_goal = SemanticGoal.from_dict(goal_data) if isinstance(goal_data, dict) else None

        return cls(
            plan_id=data.get("plan_id") or f"plan-{uuid.uuid4().hex[:8]}",
            goal=data.get("goal", ""),
            semantic_goal=sem_goal,
            primary_intent=primary_intent,
            is_conversational=is_conv,
            assumptions=data.get("assumptions", []) or [],
            entities=data.get("entities", []) or [],
            steps=steps,
            final_success_condition=data.get("final_success_condition", ""),
            risk_level=data.get("risk_level", "LOW"),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class SemanticPlanCritique:
    """Result of deterministic and semantic plan critique."""
    is_valid: bool = True
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    score: float = 1.0


@dataclass
class PlanningTelemetry:
    """Structured telemetry data for plan compilation tracking."""
    plan_id: str
    model_name: str
    latency_ms: float
    step_count: int
    validation_passed: bool
    critique_passed: bool
    revisions: int = 0
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)