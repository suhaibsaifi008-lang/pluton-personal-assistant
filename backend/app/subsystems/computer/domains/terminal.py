"""
PLUTON V2 — Terminal Domain Handler & Security Boundary
Implements canonical terminal capabilities:
terminal.execute, terminal.output, terminal.exit_code, terminal.process, terminal.stop.
Enforces security risk classification, policy boundaries, process ownership, timeout, and cancellation.
"""

from __future__ import annotations

import enum
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL

logger = logging.getLogger("pluton.computer.terminal")


class CommandRiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TerminalSecurityPolicy:
    """Security engine for analyzing and classifying shell commands."""

    CRITICAL_PATTERNS = [
        r"\bformat\b\s+[a-zA-Z]:",
        r"\bdiskpart\b",
        r"\bmkfs\b",
        r"\bvssadmin\b\s+delete\s+shadows",
        r"\bbcdedit\b",
        r"\bdel\b\s+(/f\s+|/s\s+|/q\s+)*[c-zC-Z]:\\",
        r"\brmdir\b\s+(/s\s+|/q\s+)*[c-zC-Z]:\\",
        r"\brm\s+-rf\s+[/~]",
        r"Remove-Item\s+.*-Recurse\s+.*-Force\s+[c-zC-Z]:\\",
        r"powershell(\.exe)?\s+.*-(enc|encodedcommand)\b",
        r"\[System\.Convert\]::FromBase64String",
        r"\biex\s*\(\s*(New-Object|iwr|curl|wget)\b",
        r"\breg\s+delete\s+HKLM\b",
        r"\btakeown\b\s+/f\s+[c-zC-Z]:\\Windows\b",
        r"\bicacls\b\s+[c-zC-Z]:\\Windows\b",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
    ]

    HIGH_RISK_PATTERNS = [
        r"\btaskkill\b\s+(/f\s+)*(/im\s+\*|/fi\b)",
        r"\bStop-Process\b\s+.*-Force\s+\*",
        r"\bshutdown\b\s+/[s|r|p]",
        r"\bnet\s+user\b\s+.*\/add",
        r"\bnetsh\s+firewall\b",
    ]

    @classmethod
    def classify_command(cls, command: str) -> tuple[CommandRiskLevel, str | None]:
        cmd_clean = command.strip()
        for pattern in cls.CRITICAL_PATTERNS:
            if re.search(pattern, cmd_clean, re.IGNORECASE):
                return CommandRiskLevel.CRITICAL, f"Matched critical security pattern: {pattern}"

        for pattern in cls.HIGH_RISK_PATTERNS:
            if re.search(pattern, cmd_clean, re.IGNORECASE):
                return CommandRiskLevel.HIGH, f"Matched high-risk security pattern: {pattern}"

        if any(sep in cmd_clean for sep in [";", "&&", "||", "|", ">", ">>", "`"]):
            return CommandRiskLevel.MEDIUM, "Contains command chaining, pipes, or redirection."

        return CommandRiskLevel.LOW, "Standard benign command."


class TerminalDomainHandler:
    """Canonical handler for command execution in OS terminal/shell with policy enforcement."""

    def __init__(self, policy: TerminalSecurityPolicy | None = None) -> None:
        self.policy = policy or TerminalSecurityPolicy()
        self._last_executions: dict[str, dict[str, Any]] = {}
        self._active_processes: dict[int, subprocess.Popen] = {}

    def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 30.0,
        context: ExecutionContext | None = None,
        allow_high_risk: bool = False,
    ) -> dict[str, Any]:
        """Execute a shell command with security classification, policy gating, and audit logs."""
        KERNEL.assert_authorized(context.task_id if context else None)

        if not command or not command.strip():
            return {
                "success": False,
                "command": command,
                "error": "EMPTY_COMMAND: Cannot execute empty terminal string.",
                "exit_code": -1,
                "policy_status": "DENIED",
            }

        risk_level, reason = self.policy.classify_command(command)
        logger.info("[TERMINAL] Command: '%s' | Risk: %s | Reason: %s", command, risk_level.value, reason)

        if risk_level == CommandRiskLevel.CRITICAL:
            logger.error("[TERMINAL SECURITY] Blocked CRITICAL command: %s (%s)", command, reason)
            return {
                "success": False,
                "command": command,
                "error": f"POLICY_DENIED: Critical dangerous command blocked by security policy. ({reason})",
                "risk_level": risk_level.value,
                "policy_status": "DENIED",
                "exit_code": -1,
            }

        if risk_level == CommandRiskLevel.HIGH and not allow_high_risk:
            logger.warning("[TERMINAL SECURITY] Blocked unapproved HIGH risk command: %s", command)
            return {
                "success": False,
                "command": command,
                "error": f"REQUIRES_APPROVAL: High-risk command requires explicit approval. ({reason})",
                "risk_level": risk_level.value,
                "policy_status": "REQUIRES_APPROVAL",
                "exit_code": -1,
            }

        valid_cwd = None
        if cwd:
            try:
                p_cwd = Path(cwd).resolve()
                if not p_cwd.exists() or not p_cwd.is_dir():
                    return {
                        "success": False,
                        "command": command,
                        "error": f"INVALID_CWD: Specified working directory does not exist: {cwd}",
                        "exit_code": -1,
                    }
                valid_cwd = str(p_cwd)
            except Exception as e:
                return {"success": False, "command": command, "error": f"INVALID_CWD: {e}", "exit_code": -1}

        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=valid_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self._active_processes[proc.pid] = proc

            stdout_txt, stderr_txt = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
            self._active_processes.pop(proc.pid, None)

            result = {
                "success": exit_code == 0,
                "command": command,
                "stdout": stdout_txt,
                "stderr": stderr_txt,
                "exit_code": exit_code,
                "risk_level": risk_level.value,
                "policy_status": "ALLOWED",
            }
            task_key = context.task_id if context else "global"
            self._last_executions[task_key] = result
            return result

        except subprocess.TimeoutExpired:
            if proc.pid in self._active_processes:
                proc.kill()
                self._active_processes.pop(proc.pid, None)
            return {
                "success": False,
                "command": command,
                "error": f"TIMEOUT: Command exceeded maximum execution limit of {timeout}s.",
                "exit_code": -1,
                "policy_status": "TIMEOUT",
            }
        except Exception as e:
            return {"success": False, "command": command, "error": f"EXECUTION_FAILED: {e}", "exit_code": -1}

    def output(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get output from last terminal execution."""
        KERNEL.assert_authorized(context.task_id if context else None)
        task_key = context.task_id if context else "global"
        last = self._last_executions.get(task_key, {})
        return {
            "success": bool(last),
            "stdout": last.get("stdout", ""),
            "stderr": last.get("stderr", ""),
            "exit_code": last.get("exit_code", -1),
        }

    def exit_code(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get exit code from last terminal execution."""
        KERNEL.assert_authorized(context.task_id if context else None)
        task_key = context.task_id if context else "global"
        last = self._last_executions.get(task_key, {})
        return {"success": bool(last), "exit_code": last.get("exit_code", -1)}

    def process(self, pid: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Check status of a running terminal process."""
        KERNEL.assert_authorized(context.task_id if context else None)
        proc = self._active_processes.get(pid)
        if not proc:
            return {"success": False, "pid": pid, "running": False}
        poll_res = proc.poll()
        return {"success": True, "pid": pid, "running": poll_res is None, "exit_code": poll_res}

    def stop(self, pid: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Stop a running terminal process."""
        KERNEL.assert_authorized(context.task_id if context else None)
        proc = self._active_processes.get(pid)
        if proc:
            proc.kill()
            self._active_processes.pop(pid, None)
            return {"success": True, "pid": pid, "stopped": True}
        return {"success": False, "pid": pid, "error": f"Process {pid} not found in active processes."}


TERMINAL_DOMAIN = TerminalDomainHandler()
