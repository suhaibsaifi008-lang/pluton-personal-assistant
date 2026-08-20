"""
PLUTON V2 — Dynamic Capability Schema Registry.
Exposes machine-readable contracts of available Pluton capabilities to the Semantic Planner
without hardcoding static application workflows or tool instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from app.core.contracts import CapabilityType, ExecutionTier, RiskLevel, VerificationStrategy


@dataclass(frozen=True)
class CapabilityContract:
    """Machine-readable metadata contract for a Pluton capability."""
    capability_id: str
    semantic_intent: str
    description: str
    target_required: bool
    allowed_target_types: list[str]
    parameter_schema: dict[str, Any]
    default_verification: str
    risk_level: str
    side_effect_level: str  # "NONE" (read-only), "IDEMPOTENT", "MUTATING", "HIGH_RISK"


class CapabilityRegistry:
    """Canonical provider of dynamic capability schemas for semantic planning."""

    _CAPABILITIES: dict[str, CapabilityContract] = {
        CapabilityType.CALCULATE.value: CapabilityContract(
            capability_id=CapabilityType.CALCULATE.value,
            semantic_intent="calculate",
            description="Evaluate a mathematical or arithmetic expression safely via deterministic AST evaluator.",
            target_required=False,
            allowed_target_types=["none"],
            parameter_schema={
                "expression": {"type": "string", "description": "Mathematical expression to evaluate (e.g. '25 * 4', '125 * 48', '(50 + 50) * 2')"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.SYSTEM_TIME.value: CapabilityContract(
            capability_id=CapabilityType.SYSTEM_TIME.value,
            semantic_intent="get_system_time",
            description="Read the current trusted date and time from the system clock.",
            target_required=False,
            allowed_target_types=["none"],
            parameter_schema={
                "timezone": {"type": "string", "description": "Optional timezone identifier (e.g. 'UTC', 'EST', 'Asia/Tokyo')"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.SYSTEM_DATE.value: CapabilityContract(
            capability_id=CapabilityType.SYSTEM_DATE.value,
            semantic_intent="get_system_date",
            description="Read the current trusted date from the system clock.",
            target_required=False,
            allowed_target_types=["none"],
            parameter_schema={
                "timezone": {"type": "string", "description": "Optional timezone identifier (e.g. 'UTC', 'EST')"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.APP_LAUNCH.value: CapabilityContract(
            capability_id=CapabilityType.APP_LAUNCH.value,
            semantic_intent="open_application",
            description="Launch or focus a desktop application by semantic name or executable.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target"],
            parameter_schema={
                "app_name": {"type": "string", "description": "Name of application (e.g. 'Calculator', 'Notepad', 'Spotify')"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Optional CLI arguments"},
            },
            default_verification="WINDOW_PRESENCE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.APP_CLOSE.value: CapabilityContract(
            capability_id=CapabilityType.APP_CLOSE.value,
            semantic_intent="close_window",
            description="Close a target application window gracefully.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target", "contextual_active_window"],
            parameter_schema={
                "target": {"type": "string", "description": "Application or window name to close"},
            },
            default_verification="WINDOW_ABSENCE",
            risk_level="MEDIUM",
            side_effect_level="MUTATING",
        ),
        CapabilityType.BROWSER_NAVIGATE.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_NAVIGATE.value,
            semantic_intent="navigate_browser",
            description="Navigate the browser to a destination URL or web domain.",
            target_required=True,
            allowed_target_types=["explicit_url", "explicit_name", "contextual_previous_target"],
            parameter_schema={
                "url": {"type": "string", "description": "Destination URL (e.g. 'https://youtube.com', 'http://127.0.0.1:5173')"},
                "browser": {"type": "string", "description": "Optional specific browser name (e.g. 'Brave', 'Chrome')"},
                "force_new_tab": {"type": "boolean", "description": "Whether to force opening in a new tab"},
            },
            default_verification="BROWSER_TAB_PRESENCE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.BROWSER_SEARCH.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_SEARCH.value,
            semantic_intent="search_web",
            description="Perform a web search query on a search engine.",
            target_required=True,
            allowed_target_types=["explicit_name", "none"],
            parameter_schema={
                "query": {"type": "string", "description": "Search term or question to search"},
                "engine": {"type": "string", "description": "Search engine (default 'google')"},
            },
            default_verification="BROWSER_TAB_PRESENCE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.BROWSER_GET_TITLE.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_GET_TITLE.value,
            semantic_intent="get_browser_title",
            description="Read and verify the title of the active browser tab.",
            target_required=False,
            allowed_target_types=["none", "contextual_active_tab", "explicit_name"],
            parameter_schema={},
            default_verification="BROWSER_TITLE_MATCH",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.KEYBOARD_TYPE.value: CapabilityContract(
            capability_id=CapabilityType.KEYBOARD_TYPE.value,
            semantic_intent="input_text",
            description="Type text or enter mathematical formulas into the target window or control.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_active_window", "contextual_previous_target"],
            parameter_schema={
                "text": {"type": "string", "description": "Text or formula to type (e.g. 'hello world', '125*48=')"},
                "target_window": {"type": "string", "description": "Target window semantic name"},
            },
            default_verification="UIA_READBACK",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.KEYBOARD_PRESS.value: CapabilityContract(
            capability_id=CapabilityType.KEYBOARD_PRESS.value,
            semantic_intent="hotkey",
            description="Press a specific keyboard key (e.g. 'enter', 'tab', 'escape').",
            target_required=False,
            allowed_target_types=["none", "contextual_active_window"],
            parameter_schema={
                "key": {"type": "string", "description": "Key name (e.g. 'enter', 'tab', 'esc')"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.KEYBOARD_HOTKEY.value: CapabilityContract(
            capability_id=CapabilityType.KEYBOARD_HOTKEY.value,
            semantic_intent="hotkey",
            description="Trigger a multi-key keyboard shortcut (e.g. ['ctrl', 'a'], ['ctrl', 'c']).",
            target_required=False,
            allowed_target_types=["none", "contextual_active_window"],
            parameter_schema={
                "keys": {"type": "array", "items": {"type": "string"}, "description": "List of key names to press together"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.UI_INVOKE.value: CapabilityContract(
            capability_id=CapabilityType.UI_INVOKE.value,
            semantic_intent="click_element",
            description="Invoke or click an accessible UI element via UIA pattern.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_active_window"],
            parameter_schema={
                "target": {"type": "string", "description": "Element name to invoke"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.GENERAL_ACTION.value: CapabilityContract(
            capability_id=CapabilityType.GENERAL_ACTION.value,
            semantic_intent="open_application",
            description="Execute general desktop entity resolution and action dispatch.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target"],
            parameter_schema={
                "target": {"type": "string", "description": "Entity name to act on"},
            },
            default_verification="WINDOW_PRESENCE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.FILESYSTEM_CREATE.value: CapabilityContract(
            capability_id=CapabilityType.FILESYSTEM_CREATE.value,
            semantic_intent="create_file",
            description="Create a new file with specified content inside the user workspace.",
            target_required=True,
            allowed_target_types=["explicit_path"],
            parameter_schema={
                "path": {"type": "string", "description": "File path (e.g. 'Downloads/notes.txt')"},
                "content": {"type": "string", "description": "Text content to write into file"},
            },
            default_verification="FILESYSTEM_CHECK",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.FILESYSTEM_READ.value: CapabilityContract(
            capability_id=CapabilityType.FILESYSTEM_READ.value,
            semantic_intent="read_file",
            description="Read content from a specified file.",
            target_required=True,
            allowed_target_types=["explicit_path", "contextual_last_file"],
            parameter_schema={
                "path": {"type": "string", "description": "File path to read"},
            },
            default_verification="FILESYSTEM_CHECK",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.FILESYSTEM_WRITE.value: CapabilityContract(
            capability_id=CapabilityType.FILESYSTEM_WRITE.value,
            semantic_intent="write_file",
            description="Write or append content into a file in the user workspace.",
            target_required=True,
            allowed_target_types=["explicit_path", "contextual_last_file"],
            parameter_schema={
                "path": {"type": "string", "description": "File path to write/append"},
                "content": {"type": "string", "description": "Text content to write"},
                "append": {"type": "boolean", "description": "Whether to append rather than overwrite"},
            },
            default_verification="FILESYSTEM_CHECK",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.FILESYSTEM_DELETE.value: CapabilityContract(
            capability_id=CapabilityType.FILESYSTEM_DELETE.value,
            semantic_intent="delete_file",
            description="Delete a file from the workspace filesystem.",
            target_required=True,
            allowed_target_types=["explicit_path", "contextual_last_file"],
            parameter_schema={
                "path": {"type": "string", "description": "File path to delete"},
            },
            default_verification="FILESYSTEM_CHECK",
            risk_level="HIGH",
            side_effect_level="HIGH_RISK",
        ),
        CapabilityType.FILESYSTEM_EXISTS.value: CapabilityContract(
            capability_id=CapabilityType.FILESYSTEM_EXISTS.value,
            semantic_intent="verify_file_exists",
            description="Verify whether a target file exists on disk.",
            target_required=True,
            allowed_target_types=["explicit_path", "contextual_last_file"],
            parameter_schema={
                "path": {"type": "string", "description": "File path to verify"},
            },
            default_verification="FILESYSTEM_CHECK",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.FILESYSTEM_LIST.value: CapabilityContract(
            capability_id=CapabilityType.FILESYSTEM_LIST.value,
            semantic_intent="list_files",
            description="List files in a directory.",
            target_required=False,
            allowed_target_types=["none", "explicit_path"],
            parameter_schema={
                "path": {"type": "string", "description": "Directory path (default current)"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.BROWSER_OPEN_TAB.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_OPEN_TAB.value,
            semantic_intent="open_new_tab",
            description="Open a new tab in the active browser.",
            target_required=False,
            allowed_target_types=["none", "explicit_url"],
            parameter_schema={
                "url": {"type": "string", "description": "Optional initial URL"},
            },
            default_verification="BROWSER_TAB_PRESENCE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.BROWSER_CLOSE_TAB.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_CLOSE_TAB.value,
            semantic_intent="close_current_tab",
            description="Close the active or target browser tab.",
            target_required=False,
            allowed_target_types=["none", "contextual_active_tab", "explicit_name"],
            parameter_schema={},
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="MUTATING",
        ),
        CapabilityType.BROWSER_SWITCH_TAB.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_SWITCH_TAB.value,
            semantic_intent="switch_tab",
            description="Switch focus to a specific browser tab.",
            target_required=True,
            allowed_target_types=["explicit_name", "explicit_url", "contextual_previous_target"],
            parameter_schema={
                "target": {"type": "string", "description": "Tab title or URL keyword to switch to"},
            },
            default_verification="BROWSER_TAB_PRESENCE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.BROWSER_RELOAD.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_RELOAD.value,
            semantic_intent="reload_tab",
            description="Reload the current or target browser tab.",
            target_required=False,
            allowed_target_types=["none", "contextual_active_tab", "explicit_url"],
            parameter_schema={},
            default_verification="BROWSER_TAB_PRESENCE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.BROWSER_LIST_TABS.value: CapabilityContract(
            capability_id=CapabilityType.BROWSER_LIST_TABS.value,
            semantic_intent="list_tabs",
            description="List all open browser tabs across windows.",
            target_required=False,
            allowed_target_types=["none"],
            parameter_schema={},
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.APP_FOCUS.value: CapabilityContract(
            capability_id=CapabilityType.APP_FOCUS.value,
            semantic_intent="focus_window",
            description="Bring an application or window to the foreground.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target", "contextual_application_reuse"],
            parameter_schema={
                "target": {"type": "string", "description": "Application or window name to focus"},
            },
            default_verification="WINDOW_PRESENCE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.APP_MINIMIZE.value: CapabilityContract(
            capability_id=CapabilityType.APP_MINIMIZE.value,
            semantic_intent="minimize_window",
            description="Minimize an application window to taskbar.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target", "contextual_active_window"],
            parameter_schema={
                "target": {"type": "string", "description": "Window name to minimize"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.APP_MAXIMIZE.value: CapabilityContract(
            capability_id=CapabilityType.APP_MAXIMIZE.value,
            semantic_intent="maximize_window",
            description="Maximize an application window to fill the screen.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target", "contextual_active_window"],
            parameter_schema={
                "target": {"type": "string", "description": "Window name to maximize"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.APP_RESTORE.value: CapabilityContract(
            capability_id=CapabilityType.APP_RESTORE.value,
            semantic_intent="restore_window",
            description="Restore a minimized or maximized window to normal size.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target", "contextual_active_window"],
            parameter_schema={
                "target": {"type": "string", "description": "Window name to restore"},
            },
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="IDEMPOTENT",
        ),
        CapabilityType.APP_IS_RUNNING.value: CapabilityContract(
            capability_id=CapabilityType.APP_IS_RUNNING.value,
            semantic_intent="verify_application_running",
            description="Check whether a target application or process is running.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target"],
            parameter_schema={
                "app_name": {"type": "string", "description": "Application name to verify"},
            },
            default_verification="WINDOW_PRESENCE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.TERMINAL_EXECUTE.value: CapabilityContract(
            capability_id=CapabilityType.TERMINAL_EXECUTE.value,
            semantic_intent="execute_terminal",
            description="Execute a safe shell command inside the workspace terminal.",
            target_required=True,
            allowed_target_types=["none", "explicit_name"],
            parameter_schema={
                "command": {"type": "string", "description": "Shell command to run"},
            },
            default_verification="TERMINAL_EXIT_CODE",
            risk_level="HIGH",
            side_effect_level="HIGH_RISK",
        ),
        CapabilityType.WINDOW_LIST.value: CapabilityContract(
            capability_id=CapabilityType.WINDOW_LIST.value,
            semantic_intent="list_windows",
            description="Enumerate all visible application windows on the desktop.",
            target_required=False,
            allowed_target_types=["none"],
            parameter_schema={},
            default_verification="NONE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
        CapabilityType.WINDOW_GET_STATE.value: CapabilityContract(
            capability_id=CapabilityType.WINDOW_GET_STATE.value,
            semantic_intent="get_window_state",
            description="Verify the visibility and state of a target window.",
            target_required=True,
            allowed_target_types=["explicit_name", "contextual_previous_target", "contextual_active_window"],
            parameter_schema={
                "target": {"type": "string", "description": "Window name to inspect"},
            },
            default_verification="WINDOW_PRESENCE",
            risk_level="LOW",
            side_effect_level="NONE",
        ),
    }

    _version: int = 1
    _cached_json_schema: list[dict[str, Any]] | None = None
    _cached_compact_schema: list[dict[str, Any]] | None = None

    @classmethod
    def get(cls, capability_id: str) -> CapabilityContract | None:
        return cls._CAPABILITIES.get(capability_id)

    @classmethod
    def get_capability(cls, capability_id: str) -> CapabilityContract | None:
        return cls._CAPABILITIES.get(capability_id)

    @classmethod
    def get_all_capabilities(cls) -> list[CapabilityContract]:
        return list(cls._CAPABILITIES.values())

    @classmethod
    def generate_json_schema(cls) -> list[dict[str, Any]]:
        """Generate cached machine-readable schema representation for model consumption."""
        if cls._cached_json_schema is not None:
            return cls._cached_json_schema

        schemas = []
        for cap in cls._CAPABILITIES.values():
            schemas.append({
                "capability": cap.capability_id,
                "semantic_intent": cap.semantic_intent,
                "description": cap.description,
                "target_required": cap.target_required,
                "allowed_target_types": cap.allowed_target_types,
                "parameters": cap.parameter_schema,
                "default_verification": cap.default_verification,
                "risk_level": cap.risk_level,
            })
        cls._cached_json_schema = schemas
        return schemas

    @classmethod
    def get_compact_schema(cls) -> list[dict[str, Any]]:
        """Generate high-density compact schema representation (~80% smaller token footprint)."""
        if cls._cached_compact_schema is not None:
            return cls._cached_compact_schema

        compact = []
        for cap in cls._CAPABILITIES.values():
            params = {k: v.get("description", v.get("type", "")) for k, v in cap.parameter_schema.items()}
            compact.append({
                "id": cap.capability_id,
                "intent": cap.semantic_intent,
                "desc": cap.description,
                "targets": cap.allowed_target_types,
                "params": params,
                "risk": cap.risk_level,
            })
        cls._cached_compact_schema = compact
        return compact

    @classmethod
    def invalidate_cache(cls) -> None:
        """Invalidate cached schemas when capability definitions change."""
        cls._version += 1
        cls._cached_json_schema = None
        cls._cached_compact_schema = None