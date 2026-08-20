import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse
import webbrowser

from ..security import PermissionLevel
from .base import Tool, _STRING_PROP, _schema
from .filesystem import _resolve_in_workspace
from .registry import ToolRegistry

_ALLOWED_APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "file_explorer": "explorer.exe",
}


def _browser_open_url(url: str) -> dict[str, Any]:
    cleaned = url.strip()
    if not cleaned:
        return {"error": "Empty URL."}
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"error": "Only http:// and https:// URLs are allowed."}
    try:
        opened = webbrowser.open(cleaned)
        return {"url": cleaned, "opened": bool(opened)}
    except Exception as error:
        return {"error": f"Failed to open web browser: {error}"}


def _app_launch(target: str) -> dict[str, Any]:
    cleaned = target.strip()
    if not cleaned:
        return {"error": "Target application or folder is required."}
    lowered = cleaned.lower()

    if lowered in _ALLOWED_APPS:
        app_name = _ALLOWED_APPS[lowered]
        try:
            if hasattr(os, "startfile"):
                os.startfile(app_name)
            else:
                subprocess.Popen([app_name])
            return {"target": cleaned, "launched": True, "type": "application"}
        except Exception as error:
            return {"error": f"Could not launch application '{cleaned}': {error}"}

    if lowered in ("code", "vscode", "vs code", "vs_code"):
        code_path = shutil.which("code") or shutil.which("code.cmd") or shutil.which("code.exe")
        if not code_path:
            return {"error": "VS Code ('code') was not found in system PATH."}
        try:
            subprocess.Popen([code_path])
            return {"target": "VS Code", "launched": True, "type": "application"}
        except Exception as error:
            return {"error": f"Could not launch VS Code: {error}"}

    try:
        resolved = _resolve_in_workspace(cleaned)
        if resolved.is_dir():
            if hasattr(os, "startfile"):
                os.startfile(str(resolved))
            else:
                subprocess.Popen(["explorer.exe", str(resolved)])
            return {"target": str(resolved), "launched": True, "type": "folder"}
        elif resolved.exists():
            return {"error": f"'{cleaned}' is a file, not a directory or application."}
    except ValueError as error:
        return {"error": str(error)}
    except Exception as error:
        return {"error": f"Could not open directory: {error}"}

    return {
        "error": f"'{cleaned}' is not an approved application (Notepad, Calculator, File Explorer, VS Code) or valid workspace directory."
    }


def register_browser_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "browser.open_url",
            "Open an http:// or https:// URL in the user's default desktop web browser.",
            PermissionLevel.LOW,
            _schema({"url": _STRING_PROP}, ["url"]),
            _browser_open_url,
        )
    )
    registry.register(
        Tool(
            "app.launch",
            "Launch an approved application (Notepad, Calculator, File Explorer, VS Code) or open a workspace folder in Explorer.",
            PermissionLevel.MEDIUM,
            _schema({"target": _STRING_PROP}, ["target"]),
            _app_launch,
        )
    )
