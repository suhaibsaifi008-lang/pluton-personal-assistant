"""Canonical tool execution pipeline for PLUTON agents.

Handles tool resolution, schema validation, safe thread execution,
activity persistence, and standardized response formatting.
"""
from dataclasses import dataclass
import asyncio
import json
from typing import Any

from .models import Activity
from .security import sanitize_for_storage
from .tools import Tool, ToolRegistry, validate_tool_arguments


@dataclass
class ToolExecutionResult:
    call_id: str
    name: str
    observed: dict[str, Any]
    status: str
    summary: str
    raw_arguments: Any

    @property
    def output_payload(self) -> dict[str, Any]:
        """OpenAI Responses API format."""
        return {
            "type": "function_call_output",
            "call_id": self.call_id,
            "name": self.name,
            "output": json.dumps(self.observed, default=str),
        }

    @property
    def message_payload(self) -> dict[str, Any]:
        """OpenAI Chat Completions role='tool' format."""
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "content": json.dumps(self.observed, default=str),
        }


def persist_activity(
    db,
    task_id: str,
    name: str,
    summary: str,
    status: str = "completed",
    arguments: Any = None,
    result: Any = None,
) -> None:
    """Safely persist a sanitized tool/agent activity record to the database."""
    try:
        sanitized_args = sanitize_for_storage(arguments) if arguments is not None else None
        sanitized_res = sanitize_for_storage(result) if result is not None else None
        args_str = json.dumps(sanitized_args, default=str) if sanitized_args is not None else None
        res_str = json.dumps(sanitized_res, default=str) if sanitized_res is not None else None
        activity = Activity(
            task_id=task_id,
            name=name,
            summary=summary,
            status=status,
            arguments=args_str,
            result=res_str,
        )
        db.add(activity)
        db.commit()
    except Exception:
        pass


class ToolExecutor:
    """Canonical executor providing a single execution path for all tool calls."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute_call(
        self,
        db,
        task_id: str,
        name: str,
        call_id: str,
        arguments: Any,
        approved: bool = True,
        success_summary: str | None = None,
    ) -> tuple[ToolExecutionResult, tuple[str, dict[str, Any]]]:
        """Execute a single tool call through the canonical safety and logging pipeline.

        Returns:
            (ToolExecutionResult, activity_event_tuple)
        """
        tool = self.registry.get(name)

        if not approved:
            observed = {"denied": True, "reason": "The user denied this action."}
            status = "denied"
            summary = "Denied by user."
        elif tool is None:
            observed = {"error": f"Unknown tool: '{name}'. Only canonical tools in CANONICAL_MODEL_REGISTRY are supported."}
            status = "failed"
            summary = f"Unknown tool: '{name}'"
        else:
            is_valid, err_msg, validated_args = validate_tool_arguments(tool, arguments)
            if not is_valid:
                observed = {"error": f"Tool argument validation failed: {err_msg}"}
                status = "failed"
                summary = f"Argument validation failed: {err_msg}"
            else:
                try:
                    import inspect
                    if inspect.iscoroutinefunction(tool.execute):
                        observed = await tool.execute(**validated_args)
                    else:
                        observed = await asyncio.to_thread(tool.execute, **validated_args)
                        if inspect.isawaitable(observed):
                            observed = await observed
                    status = "completed"
                    summary = success_summary or "Tool result observed by agent."
                except Exception as error:
                    observed = {"error": str(error)}
                    status = "failed"
                    summary = f"Execution error: {error}"

        persist_activity(
            db,
            task_id,
            name,
            summary,
            status=status,
            arguments=arguments,
            result=observed,
        )
        activity_event = ("activity", {"name": name, "summary": summary, "status": status})
        result = ToolExecutionResult(
            call_id=call_id,
            name=name,
            observed=observed,
            status=status,
            summary=summary,
            raw_arguments=arguments,
        )
        return result, activity_event
