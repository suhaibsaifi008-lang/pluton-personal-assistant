from typing import Any
from .base import Tool


class ToolRegistry:
    """Registry encapsulating tool registration, lookup, listing, and inspection."""

    def __init__(self, tools: dict[str, Tool] | None = None):
        self._tools: dict[str, Tool] = dict(tools) if tools else {}

    def register(self, tool: Tool, overwrite: bool = True) -> None:
        if not overwrite and tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> Tool | None:
        return self._tools.pop(name, None)

    def get(self, name: str, default: Any = None) -> Tool | Any:
        return self._tools.get(name, default)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def contains(self, name: str) -> bool:
        return name in self._tools

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    def __getitem__(self, name: str) -> Tool:
        return self._tools[name]

    def __setitem__(self, name: str, tool: Tool) -> None:
        self._tools[name] = tool

    def __delitem__(self, name: str) -> None:
        del self._tools[name]

    def keys(self):
        return self._tools.keys()

    def values(self):
        return self._tools.values()

    def items(self):
        return self._tools.items()
