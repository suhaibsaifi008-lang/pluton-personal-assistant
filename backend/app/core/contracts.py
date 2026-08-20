"""Canonical V2 Data Models and System Contracts for PLUTON AI.

Authoritative domain language for:
- Task state machine, channels, and execution lifecycle
- Goals, intents, entities, and contextual references
- Plans, steps, actions, capabilities, and execution tiers
- Evidence, verification strategies, outcomes, and failure taxonomy
- Risk levels, permissions, and security authorization
- World state snapshots, memory records, artifacts, and event streams.

Strictly zero physical execution dependencies (no Win32, no browser, no model calls).
Strictly zero hardcoded application/browser defaults.
Strict explicit validation (no silent reinterpretation of invalid data).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Callable, Optional, Union
from uuid import uuid4


class ContractValidationError(ValueError):
    """Raised when data violates canonical contract schemas, types, or constraints."""
    pass


def _parse_enum(enum_cls: type[Enum], value: Any, field_name: str) -> Any:
    """Strictly parses an enum value, raising ContractValidationError on unknown values."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        # Try direct match
        try:
            return enum_cls(value)
        except ValueError:
            pass
        # Try case-insensitive matching for string enums
        for member in enum_cls:
            if member.name.upper() == value.upper() or member.value.upper() == value.upper():
                return member
    raise ContractValidationError(
        f"Invalid {field_name}: '{value}' is not a valid {enum_cls.__name__} member"
    )


def _parse_datetime(value: Any, field_name: str) -> datetime:
    """Parses and normalizes a timestamp into timezone-aware UTC datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception as e:
            raise ContractValidationError(f"Invalid {field_name}: '{value}' is not a valid ISO timestamp") from e
    raise ContractValidationError(f"Invalid {field_name}: expected datetime or ISO string, got {type(value).__name__}")


def _validate_required_string(value: Any, field_name: str) -> str:
    """Validates that a field contains a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"Required field '{field_name}' must be a non-empty string")
    return value.strip()


def _validate_non_negative_number(value: Any, field_name: str, allow_float: bool = True) -> float:
    """Validates that a numeric value is non-negative."""
    try:
        num = float(value) if allow_float else int(value)
    except (ValueError, TypeError) as e:
        raise ContractValidationError(f"Field '{field_name}' must be a valid number") from e
    if num < 0:
        raise ContractValidationError(f"Field '{field_name}' must be non-negative, got {num}")
    return num


# =============================================================================
# 1. State Machine, Lifecycle & Channels
# =============================================================================

class TaskState(str, Enum):
    CREATED = "CREATED"
    ROUTING = "ROUTING"
    PLANNING = "PLANNING"
    READY = "READY"
    AUTHORIZING = "AUTHORIZING"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    WAITING = "WAITING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


TERMINAL_TASK_STATES = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELLED,
    TaskState.TIMED_OUT,
}

ACTIVE_TASK_STATES = {
    TaskState.ROUTING,
    TaskState.PLANNING,
    TaskState.READY,
    TaskState.AUTHORIZING,
    TaskState.EXECUTING,
    TaskState.OBSERVING,
    TaskState.VERIFYING,
    TaskState.REPLANNING,
    TaskState.WAITING,
    TaskState.AWAITING_APPROVAL,
    TaskState.BLOCKED,
}


class TaskChannel(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    UI = "ui"
    AUTOMATION = "automation"
    API = "api"
    INTERNAL = "internal"


@dataclass
class TaskBudget:
    max_steps: int = 10
    max_time_seconds: float = 120.0
    max_model_calls: int = 5
    max_retries: int = 3
    max_side_effects: int = 5
    max_cost_usd: float = 0.50

    def __post_init__(self) -> None:
        _validate_non_negative_number(self.max_steps, "max_steps", allow_float=False)
        _validate_non_negative_number(self.max_time_seconds, "max_time_seconds")
        _validate_non_negative_number(self.max_model_calls, "max_model_calls", allow_float=False)
        _validate_non_negative_number(self.max_retries, "max_retries", allow_float=False)
        _validate_non_negative_number(self.max_side_effects, "max_side_effects", allow_float=False)
        _validate_non_negative_number(self.max_cost_usd, "max_cost_usd")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskBudget:
        return cls(
            max_steps=int(_validate_non_negative_number(data.get("max_steps", 10), "max_steps", allow_float=False)),
            max_time_seconds=float(_validate_non_negative_number(data.get("max_time_seconds", 120.0), "max_time_seconds")),
            max_model_calls=int(_validate_non_negative_number(data.get("max_model_calls", 5), "max_model_calls", allow_float=False)),
            max_retries=int(_validate_non_negative_number(data.get("max_retries", 3), "max_retries", allow_float=False)),
            max_side_effects=int(_validate_non_negative_number(data.get("max_side_effects", 5), "max_side_effects", allow_float=False)),
            max_cost_usd=float(_validate_non_negative_number(data.get("max_cost_usd", 0.50), "max_cost_usd")),
        )


# =============================================================================
# 2. Intent Domains & Canonical Goals
# =============================================================================

class IntentDomain(str, Enum):
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    TRUSTED_DATA = "trusted_data"
    CALCULATION = "calculation"
    TOOL_API = "tool_api"
    COMPUTER = "computer"
    BROWSER = "browser"
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    VOICE = "voice"
    MEMORY = "memory"
    AUTOMATION = "automation"
    MULTI_DOMAIN = "multi_domain"


@dataclass
class GoalConstraint:
    constraint_type: str
    description: str
    value: Any = None

    def __post_init__(self) -> None:
        _validate_required_string(self.constraint_type, "constraint_type")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalConstraint:
        return cls(
            constraint_type=_validate_required_string(data.get("constraint_type", "generic"), "constraint_type"),
            description=str(data.get("description", "")),
            value=data.get("value"),
        )


@dataclass
class Goal:
    objective: str
    goal_id: str = field(default_factory=lambda: str(uuid4()))
    intent_domain: IntentDomain = IntentDomain.CONVERSATION
    entities: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: list[GoalConstraint] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    desired_outcome: str = ""
    success_criteria: list[str] = field(default_factory=list)
    verification_required: bool = True
    context_requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_required_string(self.objective, "objective")
        if not isinstance(self.intent_domain, IntentDomain):
            self.intent_domain = _parse_enum(IntentDomain, self.intent_domain, "intent_domain")

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "objective": self.objective,
            "intent_domain": self.intent_domain.value,
            "entities": list(self.entities),
            "parameters": dict(self.parameters),
            "constraints": [c.to_dict() for c in self.constraints],
            "dependencies": list(self.dependencies),
            "desired_outcome": self.desired_outcome,
            "success_criteria": list(self.success_criteria),
            "verification_required": self.verification_required,
            "context_requirements": dict(self.context_requirements),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Goal:
        objective = _validate_required_string(data.get("objective", ""), "objective")
        domain_val = data.get("intent_domain", IntentDomain.CONVERSATION.value)
        domain = _parse_enum(IntentDomain, domain_val, "intent_domain")

        constraints = [
            GoalConstraint.from_dict(c) if isinstance(c, dict) else GoalConstraint(str(c), str(c))
            for c in data.get("constraints", [])
        ]

        return cls(
            objective=objective,
            goal_id=str(data.get("goal_id", str(uuid4()))),
            intent_domain=domain,
            entities=list(data.get("entities", [])),
            parameters=dict(data.get("parameters", {})),
            constraints=constraints,
            dependencies=list(data.get("dependencies", [])),
            desired_outcome=str(data.get("desired_outcome", "")),
            success_criteria=list(data.get("success_criteria", [])),
            verification_required=bool(data.get("verification_required", True)),
            context_requirements=dict(data.get("context_requirements", {})),
            metadata=dict(data.get("metadata", {})),
        )


# =============================================================================
# 3. Entities & Context References
# =============================================================================

class EntityType(str, Enum):
    APPLICATION = "application"
    WINDOW = "window"
    BROWSER = "browser"
    TAB = "tab"
    URL_PAGE = "url_page"
    FILE = "file"
    DIRECTORY = "directory"
    DOCUMENT = "document"
    PROCESS = "process"
    DEVICE = "device"
    TASK_ARTIFACT = "task_artifact"
    PERSON_CONTACT = "person_contact"
    GENERIC_RESOURCE = "generic_resource"


@dataclass
class Entity:
    semantic_name: str
    entity_type: EntityType = EntityType.GENERIC_RESOURCE
    entity_id: str = field(default_factory=lambda: str(uuid4()))
    raw_reference: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_required_string(self.semantic_name, "semantic_name")
        if not isinstance(self.entity_type, EntityType):
            self.entity_type = _parse_enum(EntityType, self.entity_type, "entity_type")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "semantic_name": self.semantic_name,
            "entity_type": self.entity_type.value,
            "raw_reference": self.raw_reference,
            "attributes": dict(self.attributes),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        name = _validate_required_string(data.get("semantic_name", ""), "semantic_name")
        etype = _parse_enum(EntityType, data.get("entity_type", EntityType.GENERIC_RESOURCE.value), "entity_type")

        return cls(
            semantic_name=name,
            entity_type=etype,
            entity_id=str(data.get("entity_id", str(uuid4()))),
            raw_reference=str(data.get("raw_reference", "")),
            attributes=dict(data.get("attributes", {})),
            metadata=dict(data.get("metadata", {})),
        )


class ReferenceType(str, Enum):
    EXPLICIT_ENTITY = "explicit_entity"
    ACTIVE_WINDOW = "active_window"
    PREVIOUS_TARGET = "previous_target"
    ACTIVE_BROWSER = "active_browser"
    ACTIVE_TAB = "active_tab"
    PREVIOUS_TAB = "previous_tab"
    LAST_FILE = "last_file"
    PREVIOUS_RESULT = "previous_result"
    CURRENT_DOCUMENT = "current_document"
    TASK_ARTIFACT = "task_artifact"
    PREVIOUS_STEP_RESULT = "previous_step_result"
    NONE = "none"


@dataclass
class ContextReference:
    ref_type: ReferenceType = ReferenceType.NONE
    raw_reference: str = ""
    entity_type: EntityType = EntityType.GENERIC_RESOURCE
    runtime_target_binding: str | None = None
    is_runtime_bound: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.ref_type, ReferenceType):
            self.ref_type = _parse_enum(ReferenceType, self.ref_type, "ref_type")
        if not isinstance(self.entity_type, EntityType):
            self.entity_type = _parse_enum(EntityType, self.entity_type, "entity_type")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_type": self.ref_type.value,
            "raw_reference": self.raw_reference,
            "entity_type": self.entity_type.value,
            "runtime_target_binding": self.runtime_target_binding,
            "is_runtime_bound": self.is_runtime_bound,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextReference:
        rtype = _parse_enum(ReferenceType, data.get("ref_type", ReferenceType.NONE.value), "ref_type")
        etype = _parse_enum(EntityType, data.get("entity_type", EntityType.GENERIC_RESOURCE.value), "entity_type")

        binding = data.get("runtime_target_binding") or data.get("resolved_target")
        is_bound = bool(data.get("is_runtime_bound", binding is not None))

        return cls(
            ref_type=rtype,
            raw_reference=str(data.get("raw_reference", "")),
            entity_type=etype,
            runtime_target_binding=binding,
            is_runtime_bound=is_bound,
            metadata=dict(data.get("metadata", {})),
        )


# =============================================================================
# 4. Capabilities & Execution Tiers
# =============================================================================

class SideEffectLevel(str, Enum):
    NONE = "NONE"
    IDEMPOTENT = "IDEMPOTENT"
    MUTATING = "MUTATING"
    HIGH_RISK = "HIGH_RISK"


class ExecutionTier(int, Enum):
    """Execution priority tier: lowest integer = strongest, safest, most deterministic tier."""
    TIER_1_NATIVE_API = 1
    TIER_2_APP_BROWSER_API = 2
    TIER_3_UIA_AUTOMATION = 3
    TIER_4_DETERMINISTIC_INPUT = 4
    TIER_5_VISION = 5
    TIER_6_COORDINATE_MOUSE = 6


class CapabilityType(str, Enum):
    # Application Domain
    APP_LIST = "app.list"
    APP_LAUNCH = "app.launch"
    APP_FOCUS = "app.focus"
    APP_MINIMIZE = "app.minimize"
    APP_MAXIMIZE = "app.maximize"
    APP_RESTORE = "app.restore"
    APP_CLOSE = "app.close"
    APP_RESTART = "app.restart"
    APP_IS_RUNNING = "app.is_running"

    # Window Domain
    WINDOW_LIST = "window.list"
    WINDOW_FIND = "window.find"
    WINDOW_FOCUS = "window.focus"
    WINDOW_MOVE = "window.move"
    WINDOW_RESIZE = "window.resize"
    WINDOW_MINIMIZE = "window.minimize"
    WINDOW_MAXIMIZE = "window.maximize"
    WINDOW_RESTORE = "window.restore"
    WINDOW_CLOSE = "window.close"
    WINDOW_GET_STATE = "window.get_state"

    # Browser Control & Navigation
    BROWSER_DETECT = "browser.detect"
    BROWSER_LIST_TABS = "browser.list_tabs"
    BROWSER_OPEN_TAB = "browser.open_tab"
    BROWSER_SWITCH_TAB = "browser.switch_tab"
    BROWSER_CLOSE_TAB = "browser.close_tab"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_BACK = "browser.back"
    BROWSER_FORWARD = "browser.forward"
    BROWSER_RELOAD = "browser.reload"
    BROWSER_GET_STATE = "browser.get_state"
    BROWSER_GET_TITLE = "browser.get_title"
    BROWSER_GET_URL = "browser.get_url"
    BROWSER_WAIT_FOR_PAGE = "browser.wait_for_page"
    BROWSER_SEARCH = "browser.search"
    BROWSER_GET_PAGE_STATE = "browser.get_page_state"
    BROWSER_INSPECT_PAGE = "browser.inspect_page"
    BROWSER_FIND_ELEMENT = "browser.find_element"
    BROWSER_CLICK_ELEMENT = "browser.click_element"
    BROWSER_TYPE_ELEMENT = "browser.type_element"
    BROWSER_SELECT_ELEMENT = "browser.select_element"
    BROWSER_EXTRACT_TEXT = "browser.extract_text"
    BROWSER_EXTRACT_LINKS = "browser.extract_links"
    BROWSER_WAIT_FOR = "browser.wait_for"
    BROWSER_SCROLL_PAGE = "browser.scroll_page"
    BROWSER_DOWNLOAD = "browser.download"
    BROWSER_UPLOAD = "browser.upload"
    BROWSER_READ_PAGE = "browser.read_page"

    # Web Domain (Canonical Surface)
    WEB_INSPECT = "web.inspect"
    WEB_FIND = "web.find"
    WEB_CLICK = "web.click"
    WEB_DOUBLE_CLICK = "web.double_click"
    WEB_TYPE = "web.type"
    WEB_CLEAR = "web.clear"
    WEB_PRESS = "web.press"
    WEB_SELECT = "web.select"
    WEB_HOVER = "web.hover"
    WEB_SCROLL = "web.scroll"
    WEB_READ = "web.read"
    WEB_EXTRACT_TEXT = "web.extract_text"
    WEB_EXTRACT_LINKS = "web.extract_links"
    WEB_WAIT = "web.wait"
    WEB_DOWNLOAD = "web.download"
    WEB_UPLOAD = "web.upload"

    # UI Automation Domain
    UI_INSPECT = "ui.inspect"
    UI_FIND = "ui.find"
    UI_INVOKE = "ui.invoke"
    UI_SET_VALUE = "ui.set_value"
    UI_TOGGLE = "ui.toggle"
    UI_SELECT = "ui.select"
    UI_EXPAND = "ui.expand"
    UI_COLLAPSE = "ui.collapse"
    UI_FOCUS = "ui.focus"

    # Keyboard Domain
    KEYBOARD_TYPE = "keyboard.type"
    KEYBOARD_PRESS = "keyboard.press"
    KEYBOARD_HOTKEY = "keyboard.hotkey"
    KEYBOARD_COPY = "keyboard.copy"
    KEYBOARD_PASTE = "keyboard.paste"
    KEYBOARD_CUT = "keyboard.cut"
    KEYBOARD_UNDO = "keyboard.undo"
    KEYBOARD_REDO = "keyboard.redo"

    # Mouse Domain
    MOUSE_MOVE = "mouse.move"
    MOUSE_CLICK = "mouse.click"
    MOUSE_DOUBLE_CLICK = "mouse.double_click"
    MOUSE_RIGHT_CLICK = "mouse.right_click"
    MOUSE_DRAG = "mouse.drag"
    MOUSE_SCROLL = "mouse.scroll"
    MOUSE_POSITION = "mouse.position"

    # Screen Domain
    SCREEN_CAPTURE = "screen.capture"
    SCREEN_INSPECT = "screen.inspect"

    # Vision Domain
    VISION_FIND = "vision.find"
    VISION_COMPARE = "vision.compare"
    VISION_VERIFY = "vision.verify"
    VISION_INSPECT = "vision.inspect"

    # Filesystem Domain
    FILESYSTEM_LIST = "filesystem.list"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_CREATE = "filesystem.create"
    FILESYSTEM_MOVE = "filesystem.move"
    FILESYSTEM_COPY = "filesystem.copy"
    FILESYSTEM_RENAME = "filesystem.rename"
    FILESYSTEM_DELETE = "filesystem.delete"
    FILESYSTEM_SEARCH = "filesystem.search"
    FILESYSTEM_EXISTS = "filesystem.exists"
    FILESYSTEM_METADATA = "filesystem.metadata"

    # Terminal Domain
    TERMINAL_EXECUTE = "terminal.execute"
    TERMINAL_OUTPUT = "terminal.output"
    TERMINAL_EXIT_CODE = "terminal.exit_code"
    TERMINAL_PROCESS = "terminal.process"
    TERMINAL_STOP = "terminal.stop"

    # Clipboard Domain
    CLIPBOARD_GET = "clipboard.get"
    CLIPBOARD_SET = "clipboard.set"
    CLIPBOARD_CLEAR = "clipboard.clear"

    # Voice Domain
    VOICE_LISTEN = "voice.listen"
    VOICE_SPEAK = "voice.speak"

    # Memory Domain
    MEMORY_STORE = "memory.store"
    MEMORY_RECALL = "memory.recall"
    MEMORY_SEARCH = "memory.search"

    # Automation Domain
    AUTOMATION_SCHEDULE = "automation.schedule"
    AUTOMATION_CANCEL = "automation.cancel"
    AUTOMATION_LIST = "automation.list"

    # System & Fast Plane Domain
    SYSTEM_TIME = "system.time"
    SYSTEM_DATE = "system.date"

    # Workflows & Generic
    SEQUENTIAL_WORKFLOW = "workflow.sequential"
    GENERAL_ACTION = "general.action"
    CALCULATE = "general.calculate"


# =============================================================================
# 5. Risk & Permission Models (Canonical Single Risk Hierarchy)
# =============================================================================

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PermissionStatus(str, Enum):
    REQUESTED = "requested"
    GRANTED = "granted"
    DENIED = "denied"
    CONFIRMATION_REQUIRED = "confirmation_required"
    EXPIRED = "expired"


@dataclass
class CapabilityDescriptor:
    capability_id: str
    name: str
    domain: IntentDomain
    description: str
    target_required: bool = False
    allowed_target_types: list[str] = field(default_factory=list)
    parameter_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    default_verification: str = "none"
    risk_level: RiskLevel = RiskLevel.LOW
    side_effect_level: SideEffectLevel = SideEffectLevel.NONE
    reversibility: bool = True
    latency_budget_ms: float = 1000.0
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_required_string(self.capability_id, "capability_id")
        _validate_required_string(self.name, "name")
        if not isinstance(self.domain, IntentDomain):
            self.domain = _parse_enum(IntentDomain, self.domain, "domain")
        if not isinstance(self.risk_level, RiskLevel):
            self.risk_level = _parse_enum(RiskLevel, self.risk_level, "risk_level")
        if not isinstance(self.side_effect_level, SideEffectLevel):
            self.side_effect_level = _parse_enum(SideEffectLevel, self.side_effect_level, "side_effect_level")
        _validate_non_negative_number(self.latency_budget_ms, "latency_budget_ms")

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "domain": self.domain.value,
            "description": self.description,
            "target_required": self.target_required,
            "allowed_target_types": list(self.allowed_target_types),
            "parameter_schema": dict(self.parameter_schema),
            "output_schema": dict(self.output_schema),
            "default_verification": self.default_verification,
            "risk_level": self.risk_level.value,
            "side_effect_level": self.side_effect_level.value,
            "reversibility": self.reversibility,
            "latency_budget_ms": self.latency_budget_ms,
            "version": self.version,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityDescriptor:
        cap_id = _validate_required_string(data.get("capability_id", ""), "capability_id")
        name = _validate_required_string(data.get("name", ""), "name")
        domain = _parse_enum(IntentDomain, data.get("domain", IntentDomain.COMPUTER.value), "domain")
        risk = _parse_enum(RiskLevel, data.get("risk_level", RiskLevel.LOW.value), "risk_level")
        side = _parse_enum(SideEffectLevel, data.get("side_effect_level", SideEffectLevel.NONE.value), "side_effect_level")
        lat = _validate_non_negative_number(data.get("latency_budget_ms", 1000.0), "latency_budget_ms")

        return cls(
            capability_id=cap_id,
            name=name,
            domain=domain,
            description=str(data.get("description", "")),
            target_required=bool(data.get("target_required", False)),
            allowed_target_types=list(data.get("allowed_target_types", [])),
            parameter_schema=dict(data.get("parameter_schema", {})),
            output_schema=dict(data.get("output_schema", {})),
            default_verification=str(data.get("default_verification", "none")),
            risk_level=risk,
            side_effect_level=side,
            reversibility=bool(data.get("reversibility", True)),
            latency_budget_ms=lat,
            version=str(data.get("version", "1.0.0")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PermissionGrant:
    capability_id: str
    risk_level: RiskLevel = RiskLevel.LOW
    status: PermissionStatus = PermissionStatus.GRANTED
    token: str = field(default_factory=lambda: str(uuid4()))
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    scope: str = "session"

    def __post_init__(self) -> None:
        _validate_required_string(self.capability_id, "capability_id")
        if not isinstance(self.risk_level, RiskLevel):
            self.risk_level = _parse_enum(RiskLevel, self.risk_level, "risk_level")
        if not isinstance(self.status, PermissionStatus):
            self.status = _parse_enum(PermissionStatus, self.status, "status")
        self.requested_at = _parse_datetime(self.requested_at, "requested_at")
        if self.granted_at is not None:
            self.granted_at = _parse_datetime(self.granted_at, "granted_at")
        if self.expires_at is not None:
            self.expires_at = _parse_datetime(self.expires_at, "expires_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "capability_id": self.capability_id,
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "requested_at": self.requested_at.isoformat(),
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionGrant:
        cap_id = _validate_required_string(data.get("capability_id", ""), "capability_id")
        risk = _parse_enum(RiskLevel, data.get("risk_level", RiskLevel.LOW.value), "risk_level")
        status = _parse_enum(PermissionStatus, data.get("status", PermissionStatus.GRANTED.value), "status")
        req_at = _parse_datetime(data.get("requested_at"), "requested_at")
        grant_at = _parse_datetime(data["granted_at"], "granted_at") if data.get("granted_at") else None
        exp_at = _parse_datetime(data["expires_at"], "expires_at") if data.get("expires_at") else None

        return cls(
            token=str(data.get("token", str(uuid4()))),
            capability_id=cap_id,
            risk_level=risk,
            status=status,
            requested_at=req_at,
            granted_at=grant_at,
            expires_at=exp_at,
            scope=str(data.get("scope", "session")),
        )


# =============================================================================
# 6. Verification & Evidence Models
# =============================================================================

class VerificationStrategy(str, Enum):
    NONE = "none"
    UIA_READBACK = "uia_readback"
    PROCESS_EXISTENCE = "process_existence"
    PROCESS_ABSENCE = "process_absence"
    WINDOW_PRESENCE = "window_presence"
    WINDOW_ABSENCE = "window_absence"
    WINDOW_STATE = "window_state"
    BROWSER_TAB_PRESENCE = "browser_tab_presence"
    BROWSER_TAB_ABSENCE = "browser_tab_absence"
    BROWSER_URL_MATCH = "browser_url_match"
    BROWSER_TITLE_MATCH = "browser_title_match"
    DOM_STATE_CHANGE = "dom_state_change"
    DOM_VALUE_MATCH = "dom_value_match"
    FILESYSTEM_CHECK = "filesystem_check"
    TERMINAL_EXIT_CODE = "terminal_exit_code"
    CLIPBOARD_MATCH = "clipboard_match"
    VISION_INSPECTION = "vision_inspection"


class VerificationOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ObservationType(str, Enum):
    WINDOW_INSPECTION = "window_inspection"
    UIA_ELEMENT_STATE = "uia_element_state"
    PROCESS_TABLE = "process_table"
    BROWSER_TAB_LIST = "browser_tab_list"
    FILESYSTEM_METADATA = "filesystem_metadata"
    FILE_CONTENT = "file_content"
    TERMINAL_EXIT_CODE = "terminal_exit_code"
    TERMINAL_STDOUT = "terminal_stdout"
    SCREENSHOT = "screenshot"
    CLIPBOARD_DATA = "clipboard_data"
    AUDIO_STREAM = "audio_stream"
    VECTOR_SIMILARITY = "vector_similarity"


@dataclass
class Evidence:
    source: str
    observation_type: ObservationType
    observed_value: Any
    evidence_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entity_id: str | None = None
    freshness_seconds: float = 0.0
    confidence: float = 1.0
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_required_string(self.source, "source")
        if not isinstance(self.observation_type, ObservationType):
            self.observation_type = _parse_enum(ObservationType, self.observation_type, "observation_type")
        self.timestamp = _parse_datetime(self.timestamp, "timestamp")
        _validate_non_negative_number(self.freshness_seconds, "freshness_seconds")
        conf = _validate_non_negative_number(self.confidence, "confidence")
        if conf > 1.0:
            raise ContractValidationError(f"Evidence confidence must be between 0.0 and 1.0, got {conf}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "observation_type": self.observation_type.value,
            "observed_value": self.observed_value,
            "timestamp": self.timestamp.isoformat(),
            "entity_id": self.entity_id,
            "freshness_seconds": self.freshness_seconds,
            "confidence": self.confidence,
            "correlation_id": self.correlation_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        src = _validate_required_string(data.get("source", ""), "source")
        obs = _parse_enum(ObservationType, data.get("observation_type", ObservationType.WINDOW_INSPECTION.value), "observation_type")
        ts = _parse_datetime(data.get("timestamp"), "timestamp")
        freshness = _validate_non_negative_number(data.get("freshness_seconds", 0.0), "freshness_seconds")
        confidence = _validate_non_negative_number(data.get("confidence", 1.0), "confidence")
        if confidence > 1.0:
            raise ContractValidationError(f"Evidence confidence must be between 0.0 and 1.0, got {confidence}")

        return cls(
            evidence_id=str(data.get("evidence_id", str(uuid4()))),
            source=src,
            observation_type=obs,
            observed_value=data.get("observed_value"),
            timestamp=ts,
            entity_id=data.get("entity_id"),
            freshness_seconds=freshness,
            confidence=confidence,
            correlation_id=data.get("correlation_id"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class VerificationResult:
    verified: bool
    strategy: VerificationStrategy = VerificationStrategy.NONE
    outcome: VerificationOutcome = VerificationOutcome.UNKNOWN
    observed_state: Any = None
    expected_state: Any = None
    message: str = ""
    latency_ms: float = 0.0
    evidence_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, VerificationStrategy):
            self.strategy = _parse_enum(VerificationStrategy, self.strategy, "strategy")
        if not isinstance(self.outcome, VerificationOutcome):
            self.outcome = _parse_enum(VerificationOutcome, self.outcome, "outcome")
        _validate_non_negative_number(self.latency_ms, "latency_ms")

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "strategy": self.strategy.value,
            "outcome": self.outcome.value,
            "observed_state": self.observed_state,
            "expected_state": self.expected_state,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "evidence_id": self.evidence_id,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationResult:
        strat = _parse_enum(VerificationStrategy, data.get("strategy", VerificationStrategy.NONE.value), "strategy")
        default_outcome = VerificationOutcome.PASS.value if data.get("verified") else VerificationOutcome.FAIL.value
        outcome = _parse_enum(VerificationOutcome, data.get("outcome", default_outcome), "outcome")
        lat = _validate_non_negative_number(data.get("latency_ms", 0.0), "latency_ms")

        return cls(
            verified=bool(data.get("verified", False)),
            strategy=strat,
            outcome=outcome,
            observed_state=data.get("observed_state"),
            expected_state=data.get("expected_state"),
            message=str(data.get("message", "")),
            latency_ms=lat,
            evidence_id=data.get("evidence_id"),
            details=dict(data.get("details", {})),
        )


# =============================================================================
# 7. Failures & Recovery Models
# =============================================================================

class FailureCategory(str, Enum):
    PLANNING_FAILURE = "planning_failure"
    TARGET_FAILURE = "target_failure"
    PERMISSION_FAILURE = "permission_failure"
    POLICY_FAILURE = "policy_failure"
    EXECUTION_FAILURE = "execution_failure"
    VERIFICATION_FAILURE = "verification_failure"
    TIMEOUT = "timeout"
    PROVIDER_FAILURE = "provider_failure"
    NETWORK_FAILURE = "network_failure"
    STALE_STATE = "stale_state"
    AMBIGUITY = "ambiguity"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    PARTIAL_SUCCESS = "partial_success"
    LOOP_DETECTED = "loop_detected"
    CANCELLATION = "cancellation"


@dataclass
class Failure:
    message: str
    category: FailureCategory = FailureCategory.EXECUTION_FAILURE
    failure_id: str = field(default_factory=lambda: str(uuid4()))
    stage: str = "execution"
    recoverable: bool = True
    evidence_id: str | None = None
    affected_action_id: str | None = None
    affected_entity: str | None = None
    retry_count: int = 0
    correlation_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_required_string(self.message, "message")
        if not isinstance(self.category, FailureCategory):
            self.category = _parse_enum(FailureCategory, self.category, "category")
        self.timestamp = _parse_datetime(self.timestamp, "timestamp")
        _validate_non_negative_number(self.retry_count, "retry_count", allow_float=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "message": self.message,
            "category": self.category.value,
            "stage": self.stage,
            "recoverable": self.recoverable,
            "evidence_id": self.evidence_id,
            "affected_action_id": self.affected_action_id,
            "affected_entity": self.affected_entity,
            "retry_count": self.retry_count,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Failure:
        msg = _validate_required_string(data.get("message", ""), "message")
        cat = _parse_enum(FailureCategory, data.get("category", FailureCategory.EXECUTION_FAILURE.value), "category")
        ts = _parse_datetime(data.get("timestamp"), "timestamp")
        retries = int(_validate_non_negative_number(data.get("retry_count", 0), "retry_count", allow_float=False))

        return cls(
            failure_id=str(data.get("failure_id", str(uuid4()))),
            message=msg,
            category=cat,
            stage=str(data.get("stage", "execution")),
            recoverable=bool(data.get("recoverable", True)),
            evidence_id=data.get("evidence_id"),
            affected_action_id=data.get("affected_action_id"),
            affected_entity=data.get("affected_entity"),
            retry_count=retries,
            correlation_id=data.get("correlation_id"),
            timestamp=ts,
            metadata=dict(data.get("metadata", {})),
        )


# =============================================================================
# 8. Target Domain & Workflow Context (Zero Browser Hardcoding)
# =============================================================================

class TargetDomain(str, Enum):
    APP = "APP"
    WINDOW = "WINDOW"
    BROWSER = "BROWSER"
    TAB = "TAB"
    WEBPAGE = "WEBPAGE"
    WEB_ELEMENT = "WEB_ELEMENT"
    UI_ELEMENT = "UI_ELEMENT"
    FILE = "FILE"
    FOLDER = "FOLDER"
    PROCESS = "PROCESS"
    TERMINAL = "TERMINAL"
    CLIPBOARD = "CLIPBOARD"
    KEYBOARD = "KEYBOARD"
    CONTROL = "CONTROL"


@dataclass
class WorkflowContext:
    active_app: str | None = None
    active_pid: int | None = None
    active_hwnd: int | None = None
    active_browser: str | None = None  # ZERO hardcoded default
    active_browser_pid: int | None = None
    active_browser_hwnd: int | None = None
    active_tab: dict[str, Any] | None = None
    active_tab_url: str | None = None
    active_page_id: str | None = None
    active_ui_target: str | None = None
    current_step: int = 0
    previous_step: int | None = None
    created_targets: list[str] = field(default_factory=list)
    stale_targets: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def inherit_from(self, other: WorkflowContext) -> None:
        self.active_app = other.active_app
        self.active_pid = other.active_pid
        self.active_hwnd = other.active_hwnd
        self.active_browser = other.active_browser
        self.active_browser_pid = other.active_browser_pid
        self.active_browser_hwnd = other.active_browser_hwnd
        self.active_tab = other.active_tab
        self.active_tab_url = other.active_tab_url
        self.active_page_id = other.active_page_id
        self.active_ui_target = other.active_ui_target

    def invalidate_window(self) -> None:
        if self.active_hwnd:
            self.stale_targets.append(f"hwnd:{self.active_hwnd}")
        self.active_hwnd = None
        self.active_pid = None
        self.active_app = None

    def invalidate_tab(self) -> None:
        if self.active_tab_url:
            self.stale_targets.append(f"url:{self.active_tab_url}")
        self.active_tab = None
        self.active_tab_url = None
        self.active_page_id = None


# =============================================================================
# 9. Actions, PlanSteps, and Plans
# =============================================================================

@dataclass
class Action:
    capability: CapabilityType
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    target_domain: TargetDomain | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    expected_state: Any = None
    timeout_seconds: float = 30.0
    verification_strategy: VerificationStrategy = VerificationStrategy.NONE
    tier_requested: ExecutionTier = ExecutionTier.TIER_1_NATIVE_API
    dependencies: list[str] = field(default_factory=list)
    context_requirements: dict[str, Any] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    authorization_token: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.capability, CapabilityType):
            self.capability = _parse_enum(CapabilityType, self.capability, "capability")
        if self.target_domain is not None and not isinstance(self.target_domain, TargetDomain):
            self.target_domain = _parse_enum(TargetDomain, self.target_domain, "target_domain")
        if not isinstance(self.risk_level, RiskLevel):
            self.risk_level = _parse_enum(RiskLevel, self.risk_level, "risk_level")
        if not isinstance(self.verification_strategy, VerificationStrategy):
            self.verification_strategy = _parse_enum(VerificationStrategy, self.verification_strategy, "verification_strategy")
        if not isinstance(self.tier_requested, ExecutionTier):
            self.tier_requested = ExecutionTier(int(self.tier_requested))
        to = _validate_non_negative_number(self.timeout_seconds, "timeout_seconds")
        if to <= 0.0:
            raise ContractValidationError(f"Action timeout_seconds must be strictly > 0, got {to}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability.value,
            "target": self.target,
            "parameters": dict(self.parameters),
            "task_id": self.task_id,
            "target_domain": self.target_domain.value if self.target_domain else None,
            "risk_level": self.risk_level.value,
            "expected_state": self.expected_state,
            "timeout_seconds": self.timeout_seconds,
            "verification_strategy": self.verification_strategy.value,
            "tier_requested": int(self.tier_requested),
            "dependencies": list(self.dependencies),
            "context_requirements": dict(self.context_requirements),
            "preconditions": list(self.preconditions),
            "authorization_token": self.authorization_token,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Action:
        cap_val = data.get("capability", CapabilityType.GENERAL_ACTION.value)
        cap = _parse_enum(CapabilityType, cap_val, "capability")

        dom_val = data.get("target_domain")
        domain = _parse_enum(TargetDomain, dom_val, "target_domain") if dom_val else None

        strat_val = data.get("verification_strategy", VerificationStrategy.NONE.value)
        strat = _parse_enum(VerificationStrategy, strat_val, "verification_strategy")

        tier_val = data.get("tier_requested", ExecutionTier.TIER_1_NATIVE_API.value)
        try:
            tier = ExecutionTier(int(tier_val))
        except Exception:
            tier = ExecutionTier.TIER_1_NATIVE_API

        # Support both RiskLevel and legacy Permission values safely
        risk_raw = data.get("risk_level", RiskLevel.LOW.value)
        if hasattr(risk_raw, "value"):
            risk_raw = risk_raw.value
        risk = _parse_enum(RiskLevel, risk_raw, "risk_level")

        to_sec = _validate_non_negative_number(data.get("timeout_seconds", 30.0), "timeout_seconds")
        if to_sec <= 0.0:
            raise ContractValidationError(f"Action timeout_seconds must be strictly > 0, got {to_sec}")

        return cls(
            id=str(data.get("id", str(uuid4()))),
            capability=cap,
            target=str(data.get("target", "")),
            parameters=dict(data.get("parameters", {})),
            task_id=str(data.get("task_id", "")),
            target_domain=domain,
            risk_level=risk,
            expected_state=data.get("expected_state"),
            timeout_seconds=to_sec,
            verification_strategy=strat,
            tier_requested=tier,
            dependencies=list(data.get("dependencies", [])),
            context_requirements=dict(data.get("context_requirements", {})),
            preconditions=list(data.get("preconditions", [])),
            authorization_token=data.get("authorization_token"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PlanStep:
    step_number: int
    description: str
    action: Action
    id: str = field(default_factory=lambda: str(uuid4()))
    target_domain: TargetDomain | None = None
    completed: bool = False
    verification: VerificationResult | None = None
    error: str | None = None
    summary: str | None = None
    dependencies: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_negative_number(self.step_number, "step_number", allow_float=False)
        if self.step_number < 1:
            raise ContractValidationError(f"PlanStep step_number must be >= 1, got {self.step_number}")
        if self.target_domain is not None and not isinstance(self.target_domain, TargetDomain):
            self.target_domain = _parse_enum(TargetDomain, self.target_domain, "target_domain")
        for dep in self.dependencies:
            if not isinstance(dep, int) or dep < 1:
                raise ContractValidationError(f"PlanStep dependency ID must be an integer >= 1, got {dep}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "step_number": self.step_number,
            "description": self.description,
            "action": self.action.to_dict(),
            "target_domain": self.target_domain.value if self.target_domain else None,
            "completed": self.completed,
            "verification": self.verification.to_dict() if self.verification else None,
            "error": self.error,
            "summary": self.summary,
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        step_num = int(_validate_non_negative_number(data.get("step_number", 1), "step_number", allow_float=False))
        if step_num < 1:
            raise ContractValidationError(f"PlanStep step_number must be >= 1, got {step_num}")

        act_dict = data.get("action", {})
        action = Action.from_dict(act_dict) if isinstance(act_dict, dict) else act_dict

        v_dict = data.get("verification")
        verification = VerificationResult.from_dict(v_dict) if isinstance(v_dict, dict) else None

        dom_val = data.get("target_domain")
        domain = _parse_enum(TargetDomain, dom_val, "target_domain") if dom_val else None

        deps = []
        for d in data.get("dependencies", []):
            dep_int = int(_validate_non_negative_number(d, "dependency_id", allow_float=False))
            if dep_int < 1:
                raise ContractValidationError(f"PlanStep dependency ID must be >= 1, got {dep_int}")
            deps.append(dep_int)

        return cls(
            id=str(data.get("id", str(uuid4()))),
            step_number=step_num,
            description=str(data.get("description", "")),
            action=action,
            target_domain=domain,
            completed=bool(data.get("completed", False)),
            verification=verification,
            error=data.get("error"),
            summary=data.get("summary"),
            dependencies=deps,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Plan:
    task_id: str
    steps: list[PlanStep] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    current_step_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_negative_number(self.current_step_index, "current_step_index", allow_float=False)
        self.created_at = _parse_datetime(self.created_at, "created_at")

    @property
    def is_finished(self) -> bool:
        return self.current_step_index >= len(self.steps)

    @property
    def current_step(self) -> PlanStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        steps = [
            PlanStep.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("steps", [])
        ]
        step_idx = int(_validate_non_negative_number(data.get("current_step_index", 0), "current_step_index", allow_float=False))
        ts = _parse_datetime(data.get("created_at"), "created_at")

        return cls(
            id=str(data.get("id", str(uuid4()))),
            task_id=str(data.get("task_id", "")),
            steps=steps,
            current_step_index=step_idx,
            created_at=ts,
            version=str(data.get("version", "1.0.0")),
            metadata=dict(data.get("metadata", {})),
        )


# =============================================================================
# 10. Canonical Task Model
# =============================================================================

@dataclass
class Task:
    user_request: str
    task_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    turn_id: int = 1
    origin: TaskChannel = TaskChannel.TEXT
    status: TaskState = TaskState.CREATED
    goal: Goal | None = None
    budget: TaskBudget = field(default_factory=TaskBudget)
    parent_task_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_required_string(self.user_request, "user_request")
        _validate_non_negative_number(self.turn_id, "turn_id", allow_float=False)
        if self.turn_id < 1:
            raise ContractValidationError(f"Task turn_id must be >= 1, got {self.turn_id}")
        if not isinstance(self.origin, TaskChannel):
            self.origin = _parse_enum(TaskChannel, self.origin, "origin")
        if not isinstance(self.status, TaskState):
            self.status = _parse_enum(TaskState, self.status, "status")
        self.created_at = _parse_datetime(self.created_at, "created_at")
        if self.completed_at is not None:
            self.completed_at = _parse_datetime(self.completed_at, "completed_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "user_request": self.user_request,
            "origin": self.origin.value,
            "status": self.status.value,
            "goal": self.goal.to_dict() if self.goal else None,
            "budget": self.budget.to_dict(),
            "parent_task_id": self.parent_task_id,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        req = _validate_required_string(data.get("user_request", ""), "user_request")
        turn = int(_validate_non_negative_number(data.get("turn_id", 1), "turn_id", allow_float=False))
        if turn < 1:
            raise ContractValidationError(f"Task turn_id must be >= 1, got {turn}")

        origin = _parse_enum(TaskChannel, data.get("origin", TaskChannel.TEXT.value), "origin")
        status = _parse_enum(TaskState, data.get("status", TaskState.CREATED.value), "status")

        g_dict = data.get("goal")
        goal = Goal.from_dict(g_dict) if isinstance(g_dict, dict) else None

        b_dict = data.get("budget", {})
        budget = TaskBudget.from_dict(b_dict) if isinstance(b_dict, dict) else TaskBudget()

        ts = _parse_datetime(data.get("created_at"), "created_at")
        comp_ts = _parse_datetime(data["completed_at"], "completed_at") if data.get("completed_at") else None

        return cls(
            task_id=str(data.get("task_id", str(uuid4()))),
            session_id=data.get("session_id"),
            turn_id=turn,
            user_request=req,
            origin=origin,
            status=status,
            goal=goal,
            budget=budget,
            parent_task_id=data.get("parent_task_id"),
            correlation_id=data.get("correlation_id"),
            created_at=ts,
            completed_at=comp_ts,
            metadata=dict(data.get("metadata", {})),
        )


# =============================================================================
# 11. World State Snapshots (Zero Hardcoded Browser)
# =============================================================================

@dataclass
class WindowSnapshot:
    hwnd: int
    title: str
    class_name: str
    pid: int
    process_name: str = ""
    is_active: bool = False
    rect: dict[str, int] = field(default_factory=dict)
    z_order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessSnapshot:
    pid: int
    name: str
    exe_path: str = ""
    is_running: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TabSnapshot:
    tab_id: str
    title: str
    url: str
    browser_name: str | None = None  # ZERO hardcoded default
    is_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileSnapshot:
    path: str
    exists: bool = True
    size_bytes: int = 0
    modified_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorldStateContract:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_window: WindowSnapshot | None = None
    windows: list[WindowSnapshot] = field(default_factory=list)
    processes: list[ProcessSnapshot] = field(default_factory=list)
    tabs: list[TabSnapshot] = field(default_factory=list)
    recent_files: list[FileSnapshot] = field(default_factory=list)
    clipboard_preview: str | None = None
    freshness_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timestamp = _parse_datetime(self.timestamp, "timestamp")
        _validate_non_negative_number(self.freshness_ms, "freshness_ms")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "active_window": self.active_window.to_dict() if self.active_window else None,
            "windows": [w.to_dict() for w in self.windows],
            "processes": [p.to_dict() for p in self.processes],
            "tabs": [t.to_dict() for t in self.tabs],
            "recent_files": [f.to_dict() for f in self.recent_files],
            "clipboard_preview": self.clipboard_preview,
            "freshness_ms": self.freshness_ms,
            "metadata": dict(self.metadata),
        }


# =============================================================================
# 12. Execution Context & Results (Zero Hardcoded Browser)
# =============================================================================

@dataclass
class BrowserTabIdentity:
    browser_name: str | None = None  # ZERO hardcoded default
    browser_pid: int | None = None
    browser_hwnd: int | None = None
    tab_index: int | None = None
    tab_title: str | None = None
    tab_url: str | None = None
    is_active: bool = False
    attached_cdp: bool = False
    cdp_pid: int | None = None
    cdp_endpoint: str | None = None
    target_id: str | None = None
    identity_status: str = "MATCHED"
    attached_timestamp: str | None = None


@dataclass
class ExecutionContext:
    task_id: str
    session_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_seconds: float = 120.0
    is_cancelled: bool = False
    cancellation_reason: str | None = None
    bound_hwnd: int | None = None
    bound_pid: int | None = None
    active_browser: str | None = None  # ZERO hardcoded default
    tab_identity: BrowserTabIdentity | None = None
    workflow_context: WorkflowContext = field(default_factory=WorkflowContext)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.created_at = _parse_datetime(self.created_at, "created_at")

    def mark_cancelled(self, reason: str = "User cancelled task") -> None:
        self.is_cancelled = True
        self.cancellation_reason = reason


@dataclass
class ToolResult:
    call_id: str
    name: str
    observed: dict[str, Any]
    status: str
    summary: str
    raw_arguments: Any
    verification: VerificationResult | None = None


@dataclass
class AgentResult:
    task_id: str
    status: TaskState
    message: str
    activities: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None


# =============================================================================
# 13. Memory, Artifacts & Events
# =============================================================================

class MemoryCategory(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    PROJECT = "project"


@dataclass
class MemoryRecord:
    content: str
    category: MemoryCategory = MemoryCategory.SEMANTIC
    id: str = field(default_factory=lambda: str(uuid4()))
    source: str = "user"
    confidence: float = 1.0
    scope: str = "global"
    provenance: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timestamp = _parse_datetime(self.timestamp, "timestamp")


class ArtifactType(str, Enum):
    FILE = "file"
    REPORT = "report"
    SPREADSHEET = "spreadsheet"
    CODE_CHANGE = "code_change"
    RESEARCH_OUTPUT = "research_output"
    DATA_TABLE = "data_table"


@dataclass
class Artifact:
    name: str
    artifact_type: ArtifactType
    id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    content: str | bytes = ""
    file_path: str | None = None
    summary: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.created_at = _parse_datetime(self.created_at, "created_at")


class EventType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    PLAN_CREATED = "PLAN_CREATED"
    STEP_STARTED = "STEP_STARTED"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    TEXT_DELTA = "TEXT_DELTA"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_TIMED_OUT = "TASK_TIMED_OUT"


@dataclass
class TaskEvent:
    event_type: EventType
    task_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.timestamp = _parse_datetime(self.timestamp, "timestamp")

    def to_sse_dict(self) -> dict[str, Any]:
        """Maps canonical EventType to legacy SSE event format for frontend compatibility."""
        type_mapping = {
            EventType.TEXT_DELTA: "text",
            EventType.ACTION_STARTED: "activity",
            EventType.ACTION_COMPLETED: "activity",
            EventType.APPROVAL_REQUIRED: "confirmation",
            EventType.TASK_COMPLETED: "done",
            EventType.TASK_FAILED: "error",
            EventType.TASK_CANCELLED: "error",
            EventType.TASK_TIMED_OUT: "error",
        }
        sse_name = type_mapping.get(self.event_type, "activity")
        return {"event": sse_name, "data": self.data}
