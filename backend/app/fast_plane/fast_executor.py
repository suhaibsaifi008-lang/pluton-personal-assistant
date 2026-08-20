"""PLUTON V2 — Fast Deterministic Capability Executor.

Executes trusted fast capabilities synchronously (< 5ms) without invoking
the computer agent loop, model provider, or physical UI automation.
"""

from __future__ import annotations

import time
from typing import Any
from app.core.contracts import CapabilityType
from .math_evaluator import SafeMathEvaluator
from .system_clock import SystemClockEvaluator


class FastCapabilityExecutor:
    """Dispatches and executes deterministic fast plane capabilities."""

    @classmethod
    def can_handle(cls, capability_id: str | CapabilityType) -> bool:
        cap_val = capability_id.value if hasattr(capability_id, "value") else str(capability_id)
        return cap_val in (
            CapabilityType.CALCULATE.value,
            "system.time",
            "system.date",
            "system.clock",
        )

    @classmethod
    def execute(cls, capability_id: str | CapabilityType, parameters: dict[str, Any]) -> dict[str, Any]:
        """Executes the requested fast capability, returning a structured execution result."""
        t0 = time.perf_counter()
        cap_val = capability_id.value if hasattr(capability_id, "value") else str(capability_id)

        if cap_val == CapabilityType.CALCULATE.value:
            expr = str(parameters.get("expression") or parameters.get("target") or "")
            result = SafeMathEvaluator.evaluate(expr)
        elif cap_val in ("system.time", "system.date", "system.clock"):
            tz = parameters.get("timezone")
            result = SystemClockEvaluator.get_current_time(tz)
        else:
            result = {
                "success": False,
                "error": f"Unsupported fast capability '{cap_val}'",
            }

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        result["latency_ms"] = elapsed_ms
        return result
