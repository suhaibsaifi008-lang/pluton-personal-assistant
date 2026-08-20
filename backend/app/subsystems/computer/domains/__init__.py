"""PLUTON V2 Computer Subsystem Domain Handlers."""

from .app import APP_DOMAIN, AppDomainHandler
from .window import WINDOW_DOMAIN, WindowDomainHandler
from .browser import BROWSER_DOMAIN, BrowserDomainHandler
from .web import WEB_DOMAIN, WebDomainHandler
from .ui import UI_DOMAIN, UIDomainHandler
from .keyboard import KEYBOARD_DOMAIN, KeyboardDomainHandler
from .mouse import MOUSE_DOMAIN, MouseDomainHandler
from .screen import SCREEN_DOMAIN, ScreenDomainHandler
from .vision import VISION_DOMAIN, VisionDomainHandler
from .filesystem import FILESYSTEM_DOMAIN, FilesystemDomainHandler
from .terminal import TERMINAL_DOMAIN, TerminalDomainHandler
from .clipboard import CLIPBOARD_DOMAIN, ClipboardDomainHandler

__all__ = [
    "APP_DOMAIN",
    "AppDomainHandler",
    "WINDOW_DOMAIN",
    "WindowDomainHandler",
    "BROWSER_DOMAIN",
    "BrowserDomainHandler",
    "WEB_DOMAIN",
    "WebDomainHandler",
    "UI_DOMAIN",
    "UIDomainHandler",
    "KEYBOARD_DOMAIN",
    "KeyboardDomainHandler",
    "MOUSE_DOMAIN",
    "MouseDomainHandler",
    "SCREEN_DOMAIN",
    "ScreenDomainHandler",
    "VISION_DOMAIN",
    "VisionDomainHandler",
    "FILESYSTEM_DOMAIN",
    "FilesystemDomainHandler",
    "TERMINAL_DOMAIN",
    "TerminalDomainHandler",
    "CLIPBOARD_DOMAIN",
    "ClipboardDomainHandler",
]
