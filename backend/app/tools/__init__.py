"""Typed tool registry and domain tool modules for PLUTON."""
import os
import subprocess
from typing import Any
import webbrowser

from .base import Tool, validate_tool_arguments, _schema
from .browser import (
    _ALLOWED_APPS,
    _app_launch,
    _browser_open_url,
    register_browser_tools,
)
from .computer import (
    _close_browser_tab,
    _close_window,
    _get_active_window,
    _gui_action_workflow,
    _hotkey,
    _inspect_screen,
    _inspect_ui_tree,
    _key_press,
    _keyboard_type,
    _launch_app,
    _list_browser_tabs,
    _list_windows,
    _locate_element,
    _mouse_click,
    _mouse_move,
    _screenshot,
    _scroll,
    _switch_browser_tab,
    _switch_window,
    _ui_action,
    _verify_screen_change,
    register_computer_tools,
)
from .uia_engine import UIA_ENGINE, UIAutomationEngine
from .computer_router import ACTION_ROUTER, ComputerActionRouter



from .filesystem import (
    _list_dir,
    _read_file,
    _resolve_in_workspace,
    _workspace,
    _write_file,
    register_filesystem_tools,
)
from .memory import (
    _memory_recall,
    _memory_save,
    recall_memories,
    register_memory_tools,
)
from .registry import ToolRegistry
from .system import (
    _clock,
    _now,
    _system_info,
    register_system_tools,
)
from .terminal import (
    _DENIED_COMMANDS,
    _run_command,
    register_terminal_tools,
)
from .web import (
    USER_AGENT,
    _strip_tags,
    _web_fetch,
    _web_search,
    register_web_tools,
)


def _get_tools() -> ToolRegistry:
    from ..capabilities.model_registry import CANONICAL_MODEL_REGISTRY
    return CANONICAL_MODEL_REGISTRY


class _LazyCanonicalRegistry:
    """Lazy proxy ensuring TOOLS delegates strictly to CANONICAL_MODEL_REGISTRY without module load cycle."""
    def get(self, name: str) -> Any:
        return _get_tools().get(name)
    def list(self) -> list[Any]:
        return _get_tools().list()
    def register(self, tool: Any) -> None:
        _get_tools().register(tool)
    def __getattr__(self, name: str) -> Any:
        return getattr(_get_tools(), name)
    def __iter__(self):
        return iter(_get_tools().list())


TOOLS: Any = _LazyCanonicalRegistry()
default_tool_registry: Any = TOOLS


def tool_metadata() -> list[dict[str, Any]]:
    return [
        {"name": tool.name, "description": tool.description, "permission": tool.permission.value}
        for tool in _get_tools().list()
    ]


__all__ = [
    "Tool",
    "ToolRegistry",
    "validate_tool_arguments",
    "recall_memories",
    "_memory_save",
    "_memory_recall",
    "_workspace",
    "_resolve_in_workspace",
    "_read_file",
    "_write_file",
    "_list_dir",
    "_run_command",
    "_browser_open_url",
    "_app_launch",
    "_web_search",
    "_web_fetch",
    "_system_info",
    "_clock",
    "_now",
    "tool_metadata",
    "register_computer_tools",
    "_screenshot",
    "_inspect_screen",
    "_locate_element",
    "_verify_screen_change",
    "_gui_action_workflow",
    "_get_active_window",
    "_mouse_move",
    "_mouse_click",
    "_scroll",
    "_keyboard_type",
    "_key_press",
    "_hotkey",
    "_launch_app",
    "TOOLS",
    "default_tool_registry",
    "os",
    "webbrowser",
]




