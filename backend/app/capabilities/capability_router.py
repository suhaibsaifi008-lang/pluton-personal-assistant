"""PLUTON V2 Canonical Capability Execution Router.

Enforces the strict execution hierarchy:
  Tier 1: Native OS API
  Tier 2: Application / Browser API
  Tier 3: UI Automation (UIA)
  Tier 4: Deterministic Keyboard Input
  Tier 5: Vision Inspection
  Tier 6: Coordinate Mouse (Absolute last resort fallback)

The LLM / Planner plans in terms of high-level Capabilities and Actions.
The CapabilityRouter selects and executes the safest, highest-tier implementation.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.contracts import (
    Action,
    ExecutionContext,
    Plan,
    ToolResult,
)
from app.verification import VERIFICATION_ENGINE

logger = logging.getLogger("pluton.capabilities")


class CapabilityRouter:
    """Canonical executor for PLUTON capabilities."""

    def __init__(self, uia_engine: Any = None, verifier: Any = None) -> None:
        self._uia = uia_engine
        self._verifier = verifier or VERIFICATION_ENGINE

    @property
    def uia(self) -> Any:
        if self._uia is None:
            from app.tools.uia_engine import UIA_ENGINE
            self._uia = UIA_ENGINE
        return self._uia

    # -------------------------------------------------------------------------
    # Intent Resolution (High-Level Request -> Structured Plan)
    # -------------------------------------------------------------------------

    def plan_request(self, request_text: str, context: ExecutionContext) -> Plan:
        """Parse natural language request into a typed Plan containing Actions via Semantic Planner / Router."""
        from app.planning.semantic import PLANNER_ROUTER
        return PLANNER_ROUTER.plan_request(request_text, context)

    # -------------------------------------------------------------------------
    # Execution Dispatcher (Delegates to Canonical Computer Engine)
    # -------------------------------------------------------------------------

    async def execute_action(self, action: Action, context: ExecutionContext) -> ToolResult:
        """Execute action following strict tier ordering through canonical Universal Computer Engine."""
        from app.subsystems.computer.engine import COMPUTER_ENGINE
        return await COMPUTER_ENGINE.execute_action(action, context)


CAPABILITY_ROUTER = CapabilityRouter()