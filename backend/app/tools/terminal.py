import shlex
import subprocess
from typing import Any

from ..config import get_settings
from ..security import PermissionLevel
from .base import Tool, _STRING_PROP, _schema
from .registry import ToolRegistry

# Deny-list for terminal commands. Terminal access is HIGH permission (the user
# approves every invocation) but we still refuse destructive primitives outright.
_DENIED_COMMANDS: tuple[str, ...] = (
    "rm ", "rmdir ", "rm -", "rd /s", "del /f", "del /s", "erase ", "format ",
    "diskpart", "shutdown", "restart ", "mkfs", "fdisk", "dd ", "mount ",
    "chkdsk /f", "reg delete", "sc delete", "schtasks /delete", "net user",
    "Remove-Item", "Clear-Content", "Set-Content", "Stop-Process", "restart-computer",
    "stop-computer", "powershell", "pwsh", "cmd /c", "cmd /k", "> ", ">> ", "| ",
    "&&", "||", "attrib -r", "icacls", "cacls", "takeown", "subst",
)


def _run_command(command: str) -> dict[str, Any]:
    settings = get_settings()
    text = command.strip()
    if not text:
        return {"error": "Empty command."}
    lowered = text.lower()
    for pattern in _DENIED_COMMANDS:
        if pattern.lower() in lowered:
            return {"denied": True, "reason": f"PLUTON blocks potentially destructive command pattern: '{pattern.strip()}'."}
    try:
        parts = shlex.split(text, posix=False)
    except ValueError as error:
        return {"error": f"Could not parse command: {error}"}
    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=settings.terminal_timeout_seconds,
            cwd=settings.allowed_workspace,
            shell=False,
        )
    except FileNotFoundError:
        return {"error": f"Command not found: {parts[0]}"}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {settings.terminal_timeout_seconds:.0f} seconds."}
    except OSError as error:
        return {"error": str(error)}
    output = f"{result.stdout}\n{result.stderr}".strip()
    limit = settings.max_tool_output_chars
    if len(output) > limit:
        output = f"{output[:limit]}\n...[truncated]"
    return {"command": text, "exit_code": result.returncode, "output": output}


def register_terminal_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "terminal.run",
            "Run a single non-interactive shell command in the approved workspace. Destructive or privileged commands are blocked. The user must approve this action.",
            PermissionLevel.HIGH,
            _schema({"command": _STRING_PROP}, ["command"]),
            _run_command,
        )
    )
