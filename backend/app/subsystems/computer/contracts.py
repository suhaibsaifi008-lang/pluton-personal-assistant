"""
PLUTON V2 — Universal Computer Subsystem Contracts
Defines schemas, target specifications, domain interfaces, and execution contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ComputerDomain(str, Enum):
    APP = "app"
    WINDOW = "window"
    BROWSER = "browser"
    WEB = "web"
    UI = "ui"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    SCREEN = "screen"
    VISION = "vision"
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    CLIPBOARD = "clipboard"


class TargetResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    TARGET_FOUND = "resolved"
    TARGET_NOT_FOUND = "target_not_found"
    AMBIGUOUS_TARGET = "ambiguous_target"
    STALE_TARGET = "stale_target"
    INVALID_TARGET = "invalid_target"


@dataclass
class TargetSpec:
    """Specification describing a target element, window, tab, or application."""
    semantic_name: Optional[str] = None
    exact_text: Optional[str] = None
    normalized_text: Optional[str] = None
    app_identity: Optional[str] = None
    pid: Optional[int] = None
    hwnd: Optional[int] = None
    browser_name: Optional[str] = None
    tab_title: Optional[str] = None
    url: Optional[str] = None
    automation_id: Optional[str] = None
    control_type: Optional[str] = None
    dom_selector: Optional[str] = None
    raw_query: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedTarget:
    """Concrete target resolved with complete runtime handles and metadata."""
    target_id: str
    name: str
    domain: ComputerDomain
    pid: Optional[int] = None
    hwnd: Optional[int] = None
    automation_id: Optional[str] = None
    control_type: Optional[str] = None
    bounds: Optional[tuple[int, int, int, int]] = None  # (left, top, width, height)
    center: Optional[tuple[int, int]] = None
    browser_tab_id: Optional[str] = None
    url: Optional[str] = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    native_handle: Any = None


@dataclass
class WebTarget:
    """Canonical representation of a resolved in-page web element."""
    browser_name: str = "Brave"
    browser_pid: int | None = None
    browser_hwnd: int | None = None
    tab_index: int | None = None
    tab_title: str | None = None
    tab_url: str | None = None
    page_id: str | None = None
    element_id: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    text: str | None = None
    selector: str | None = None
    confidence: float = 1.0
    resolver_source: str = "dom_selector"  # "accessible_name", "role_name", "label", "placeholder", "dom_selector", "uia_tree"
    visible: bool = True
    enabled: bool = True
    bounds: tuple[int, int, int, int] | None = None  # (left, top, width, height)
    value: str | None = None
    checked: bool | None = None
    selected_option: str | None = None


@dataclass
class TargetResolutionResult:
    """Outcome of resolving a TargetSpec."""
    status: TargetResolutionStatus
    target: Optional[ResolvedTarget] = None
    candidates: list[ResolvedTarget] = field(default_factory=list)
    reason: str = ""


@dataclass
class PerformanceMetrics:
    """Telemetry baseline metrics for computer actions."""
    strategy_selected: str = ""
    execution_tier: str = ""
    target_resolution_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    verification_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    fallback_count: int = 0
    vision_used: bool = False
    mouse_used: bool = False
    legacy_api_used: bool = False
