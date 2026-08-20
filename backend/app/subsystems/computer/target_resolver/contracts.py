"""
PLUTON V2 — Target Resolver Contracts & Data Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..contracts import (
    ComputerDomain,
    PerformanceMetrics,
    ResolvedTarget,
    TargetResolutionStatus,
    TargetSpec,
    WebTarget,
)


class TargetType(str, Enum):
    EXISTING_WINDOW = "existing_window"
    EXISTING_BROWSER_TAB = "existing_browser_tab"
    LOCAL_WEB_SERVICE = "local_web_service"
    INSTALLED_DESKTOP_APP = "installed_desktop_app"
    PUBLIC_WEB_DOMAIN = "public_web_domain"
    FILESYSTEM_PATH = "filesystem_path"
    SEARCH_QUERY = "search_query"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TargetCandidate:
    """Individual candidate discovered across environment sources."""
    target_type: TargetType
    identity: str                       # e.g. "http://127.0.0.1:5173", "calc.exe", "HWND:722024"
    name: str                           # Display title or label
    source: str                         # "local_web", "browser_tab", "window", "desktop_app", "domain", "filesystem"
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0                  # Ranking confidence value [0.0 - 1.0]
    matched_tokens: tuple[str, ...] = ()


@dataclass
class TargetResolutionResult:
    """Outcome of resolving a target query or TargetSpec."""
    status: TargetResolutionStatus
    target: Optional[ResolvedTarget] = None
    candidates: list[ResolvedTarget] = field(default_factory=list)
    reason: str = ""
    selected_candidate: Optional[TargetCandidate] = None
    all_candidates: tuple[TargetCandidate, ...] = ()
    is_ambiguous: bool = False
    refusal_reason: Optional[str] = None
    recommended_capability: Optional[str] = None
    bound_action_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalServiceInfo:
    """Lightweight summary of an active local development or web service."""
    host: str = "127.0.0.1"
    port: int = 0
    protocol: str = "http"
    title: Optional[str] = None
    application_name: Optional[str] = None
    pid: Optional[int] = None
    url: str = ""