from __future__ import annotations

from abc import ABC, abstractmethod
import base64
from dataclasses import dataclass, field
import mimetypes
from pathlib import Path
from typing import Any, AsyncIterator



class ProviderError(Exception):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderVisionUnsupportedError(ProviderError):
    pass


def image_to_data_uri(image_source: str) -> str:
    """Convert a file path or existing data URI to a valid base64 data URI string."""
    cleaned = image_source.strip()
    if cleaned.startswith("data:image/") or cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned

    file_path = Path(cleaned)
    if not file_path.is_file():
        raise FileNotFoundError(f"Image file not found: '{cleaned}'")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"

    raw_bytes = file_path.read_bytes()
    encoded = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderRequest:
    message: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    previous_response_id: str | None = None
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderResponse:
    response_id: str
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderEvent:
    kind: str
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    response_id: str = ""
    error: str = ""


class AIProvider(ABC):
    name: str

    @property
    @abstractmethod
    def model(self) -> str:
        ...

    @property
    def supports_vision(self) -> bool:
        """Whether the provider/model can process multimodal image inputs."""
        return False

    @abstractmethod
    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        ...

    async def stream_respond(self, request: ProviderRequest) -> AsyncIterator[ProviderEvent]:
        response = await self.respond(request)
        if response.text:
            yield ProviderEvent(kind="text_delta", text=response.text)
        yield ProviderEvent(kind="tool_calls", tool_calls=response.tool_calls, response_id=response.response_id)

    async def stream_text(self, request: ProviderRequest) -> AsyncIterator[str]:
        async for event in self.stream_respond(request):
            if event.kind == "text_delta" and event.text:
                yield event.text


OPENAI_INSTRUCTIONS = (
    "You are PLUTON, an autonomous desktop AI agent running locally on the user's computer with structured UI Automation, native OS control, browser management, and computer control capabilities.\n\n"
    "CRITICAL CAPABILITY HIERARCHY & CONTROL RULES:\n"
    "1. STRUCTURED CANONICAL TOOLS FIRST:\n"
    "   - Always prioritize structured canonical tools over vision.\n"
    "   - For opening URLs or web destinations (e.g. 'open Google', 'navigate to GitHub'), use browser.navigate with browser='Brave'.\n"
    "   - For managing browser tabs (listing, switching, closing), use browser.list_tabs, browser.switch_tab, or browser.close_tab.\n"
    "   - For interacting with web pages (searching, clicking, typing), follow: browser.navigate -> browser.inspect_page -> browser.type -> browser.click/keyboard.press -> browser.inspect_page.\n"
    "   - For desktop windows and apps, use app.launch, app.close, window.list, window.focus, window.minimize, and window.close.\n"
    "   - For interacting with structured desktop controls (buttons, textboxes), use ui.inspect, ui.find, ui.invoke, and ui.set_value.\n"
    "   - Use vision/screenshot coordinates (vision.inspect, screen.capture) ONLY as a final fallback when structured UI controls are unavailable.\n"
    "2. APPLICATION & WINDOW SAFETY:\n"
    "   - If the target application window is already running or visible, switch to it using window.focus rather than launching duplicate instances.\n"
    "   - NEVER substitute generic destructive keyboard shortcuts like ['ctrl', 'w'] or ['alt', 'f4'] when asked to close a specific tab or window.\n"
    "3. VERIFICATION & COMPLETION:\n"
    "   - Never claim a tool succeeded unless its execution result confirms success.\n"
    "   - After performing the requested action (e.g. typing query and submitting search), inspect or observe the resulting page state.\n"
    "   - Once the user's requested action is accomplished and verified (e.g. search query submitted and results visible), CONCLUDE IMMEDIATELY with your final response. Do NOT call web.search, do NOT click search results, and do NOT open redundant tabs unless explicitly requested by the user.\n"
    "4. For terminal tasks, execute safe commands via terminal.execute.\n"
    "5. If the user shares information worth remembering, save it with memory.save."
)









