"""PLUTON V2 — Front-Door Router Contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from app.core.contracts import IntentDomain, Task


@dataclass
class RouteContext:
    session_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RouteDecision:
    domain: IntentDomain
    confidence: float = 1.0
    capability_id: str | None = None
    reason: str = ""
    requires_model: bool = False
    requires_computer_agent: bool = False
    requires_current_data: bool = False
    is_ambiguous: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "confidence": self.confidence,
            "capability_id": self.capability_id,
            "reason": self.reason,
            "requires_model": self.requires_model,
            "requires_computer_agent": self.requires_computer_agent,
            "requires_current_data": self.requires_current_data,
            "is_ambiguous": self.is_ambiguous,
            "parameters": dict(self.parameters),
            "task_id": self.task_id,
        }
