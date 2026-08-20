from enum import Enum
import re
from typing import Any


class PermissionLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def requires_confirmation(level: PermissionLevel) -> bool:
    return level == PermissionLevel.HIGH


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|password|secret|token|auth|authorization|cookie|credential|private[_-]?key)"
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(Bearer\s+[a-zA-Z0-9_\-\.]+|freellmapi-[a-zA-Z0-9]+|sk-[a-zA-Z0-9_\-]+)"
)


def sanitize_for_storage(data: Any) -> Any:
    """Recursively redact secrets, credentials, tokens, authorization headers, and raw base64 image data from data before persistence."""
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if _SENSITIVE_KEY_PATTERN.search(str(key)):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = sanitize_for_storage(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_storage(item) for item in data]
    elif isinstance(data, str):
        if data.startswith("data:image/") and ";base64," in data:
            return "[IMAGE_DATA]"
        return _SECRET_VALUE_PATTERN.sub("[REDACTED]", data)
    return data


