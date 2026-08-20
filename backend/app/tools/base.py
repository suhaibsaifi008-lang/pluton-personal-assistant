from dataclasses import dataclass
from typing import Any, Callable
import json

from ..security import PermissionLevel

_STRING_PROP = {"type": "string"}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    permission: PermissionLevel
    input_schema: dict[str, Any]
    execute: Callable[..., dict[str, Any]]


def validate_tool_arguments(tool: Tool, raw_arguments: Any) -> tuple[bool, str | None, dict[str, Any]]:
    """Validate raw tool arguments against tool's input_schema.
    Returns (is_valid, error_message, parsed_arguments_dict).
    """
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except Exception as e:
            return False, f"Malformed JSON arguments: {e}", {}
    elif isinstance(raw_arguments, dict):
        parsed = dict(raw_arguments)
    else:
        return False, f"Expected arguments object, got {type(raw_arguments).__name__}", {}

    schema = tool.input_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    allow_additional = schema.get("additionalProperties", True)

    for req_field in required:
        if req_field not in parsed:
            return False, f"Missing required argument: '{req_field}'", parsed

    if not allow_additional:
        unexpected = set(parsed.keys()) - set(properties.keys())
        if unexpected:
            return False, f"Unexpected argument(s): {', '.join(sorted(unexpected))}", parsed

    type_map = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
    }
    for field_name, value in parsed.items():
        if field_name in properties and value is not None:
            expected_type_str = properties[field_name].get("type")
            if expected_type_str in type_map:
                allowed_types = type_map[expected_type_str]
                if expected_type_str in ("integer", "number") and isinstance(value, bool):
                    return False, f"Argument '{field_name}' must be {expected_type_str}, got boolean", parsed
                if not isinstance(value, allowed_types):
                    return False, f"Argument '{field_name}' must be of type {expected_type_str}, got {type(value).__name__}", parsed

    return True, None, parsed
