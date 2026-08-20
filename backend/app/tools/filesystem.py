from pathlib import Path
from typing import Any

from ..config import get_settings
from ..security import PermissionLevel
from .base import Tool, _STRING_PROP, _schema
from .registry import ToolRegistry


def _workspace() -> Path:
    return get_settings().allowed_workspace.resolve()


def _resolve_in_workspace(path: str) -> Path:
    # Look up _workspace via package root if available to support test monkeypatching
    try:
        import app.tools as _tools_pkg
        root = _tools_pkg._workspace()
    except Exception:
        root = _workspace()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    target = candidate.resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path is outside Pluton's approved workspace.")
    return target



def _read_file(path: str) -> dict[str, Any]:
    target = _resolve_in_workspace(path)
    if not target.is_file():
        raise ValueError(f"File does not exist: {target}")
    return {"path": str(target), "content": target.read_text(encoding="utf-8")}


def _write_file(path: str, content: str) -> dict[str, Any]:
    target = _resolve_in_workspace(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(target), "wrote": len(content), "overwrote": target.exists()}


def _list_dir(path: str = ".") -> dict[str, Any]:
    target_path = path if path and path.strip() else "."
    try:
        target = _resolve_in_workspace(target_path)
    except ValueError as error:
        return {"error": str(error)}
    if not target.exists():
        return {"error": f"Directory does not exist: {target_path}"}
    if not target.is_dir():
        return {"error": f"Path is not a directory: {target_path}"}

    entries: list[dict[str, Any]] = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                is_dir = child.is_dir()
                entries.append({
                    "name": child.name,
                    "type": "directory" if is_dir else "file",
                    "size_bytes": None if is_dir else child.stat().st_size,
                })
            except (OSError, PermissionError):
                continue
        return {
            "path": str(target),
            "entries": entries,
            "count": len(entries),
        }
    except Exception as error:
        return {"error": f"Could not list directory: {error}"}


def register_filesystem_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "filesystem.read",
            "Read a UTF-8 text file in the approved workspace.",
            PermissionLevel.LOW,
            _schema({"path": _STRING_PROP}, ["path"]),
            _read_file,
        )
    )
    registry.register(
        Tool(
            "filesystem.write",
            "Create or overwrite a UTF-8 text file inside the approved workspace.",
            PermissionLevel.MEDIUM,
            _schema({"path": _STRING_PROP, "content": _STRING_PROP}, ["path", "content"]),
            _write_file,
        )
    )
    registry.register(
        Tool(
            "filesystem.list_dir",
            "List files and directories within the approved workspace.",
            PermissionLevel.LOW,
            _schema({"path": _STRING_PROP}, []),
            _list_dir,
        )
    )
