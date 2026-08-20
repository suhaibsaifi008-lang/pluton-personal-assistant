"""
PLUTON V2 — Canonical Engine Conformance Verifier & Runtime Registry
Validates all canonical computer engines and domain handlers against their Protocol contracts at startup.
Fails fast with structured CANONICAL_INTERFACE_ERROR if any required method is missing.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Type

from .interfaces import (
    CanonicalInterfaceError,
    IAppDomain,
    IBrowserDomain,
    IClipboardDomain,
    IFilesystemDomain,
    IKeyboardDomain,
    IMouseDomain,
    IScreenDomain,
    ITerminalDomain,
    IUIADomain,
    IUIAEngine,
    IVisionDomain,
    IWebDomain,
    IWindowDomain,
)

logger = logging.getLogger("pluton.computer.conformance")


class EngineConformanceVerifier:
    """Automated validator ensuring all canonical subsystems conform strictly to their interface contracts."""

    _REQUIRED_PROTOCOLS: list[tuple[str, str, Type[Any]]] = [
        ("UIAEngine", "app.tools.uia_engine.UIA_ENGINE", IUIAEngine),
        ("WindowDomain", "app.subsystems.computer.domains.window.WINDOW_DOMAIN", IWindowDomain),
        ("UIDomain", "app.subsystems.computer.domains.ui.UI_DOMAIN", IUIADomain),
        ("BrowserDomain", "app.subsystems.computer.domains.browser.BROWSER_DOMAIN", IBrowserDomain),
        ("WebDomain", "app.subsystems.computer.domains.web.WEB_DOMAIN", IWebDomain),
        ("KeyboardDomain", "app.subsystems.computer.domains.keyboard.KEYBOARD_DOMAIN", IKeyboardDomain),
        ("MouseDomain", "app.subsystems.computer.domains.mouse.MOUSE_DOMAIN", IMouseDomain),
        ("ScreenDomain", "app.subsystems.computer.domains.screen.SCREEN_DOMAIN", IScreenDomain),
        ("VisionDomain", "app.subsystems.computer.domains.vision.VISION_DOMAIN", IVisionDomain),
        ("FilesystemDomain", "app.subsystems.computer.domains.filesystem.FILESYSTEM_DOMAIN", IFilesystemDomain),
        ("TerminalDomain", "app.subsystems.computer.domains.terminal.TERMINAL_DOMAIN", ITerminalDomain),
        ("ClipboardDomain", "app.subsystems.computer.domains.clipboard.CLIPBOARD_DOMAIN", IClipboardDomain),
        ("AppDomain", "app.subsystems.computer.domains.app.APP_DOMAIN", IAppDomain),
    ]

    @staticmethod
    def get_protocol_methods(protocol_cls: Type[Any]) -> list[str]:
        """Extract all required method names declared on a Protocol class."""
        methods = []
        for name in dir(protocol_cls):
            if name.startswith("_"):
                continue
            val = getattr(protocol_cls, name)
            if callable(val) or inspect.isfunction(val) or inspect.iscoroutinefunction(val):
                methods.append(name)
        return methods

    @classmethod
    def verify_instance(cls, instance: Any, protocol_cls: Type[Any], name: str) -> dict[str, Any]:
        """Verify an individual engine instance conforms to its declared protocol."""
        required = cls.get_protocol_methods(protocol_cls)
        missing = []
        available = []

        for m in required:
            if not hasattr(instance, m) or not callable(getattr(instance, m)):
                missing.append(m)
            else:
                available.append(m)

        if missing:
            msg = f"CANONICAL_INTERFACE_ERROR: Engine '{name}' ({instance.__class__.__name__}) is missing required methods: {missing}"
            logger.error(msg)
            raise CanonicalInterfaceError(msg)

        all_instance_methods = [
            m for m in dir(instance)
            if not m.startswith("_") and callable(getattr(instance, m))
        ]

        return {
            "engine": name,
            "class": instance.__class__.__name__,
            "module": instance.__class__.__module__,
            "conforms": True,
            "required_methods": required,
            "missing_methods": missing,
            "available_methods": all_instance_methods,
        }

    @classmethod
    def audit_all(cls) -> dict[str, Any]:
        """Run full startup conformance audit across all registered canonical engines."""
        from app.tools.uia_engine import UIA_ENGINE
        from app.subsystems.computer.domains.window import WINDOW_DOMAIN
        from app.subsystems.computer.domains.ui import UI_DOMAIN
        from app.subsystems.computer.domains.browser import BROWSER_DOMAIN
        from app.subsystems.computer.domains.web import WEB_DOMAIN
        from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN
        from app.subsystems.computer.domains.mouse import MOUSE_DOMAIN
        from app.subsystems.computer.domains.screen import SCREEN_DOMAIN
        from app.subsystems.computer.domains.vision import VISION_DOMAIN
        from app.subsystems.computer.domains.filesystem import FILESYSTEM_DOMAIN
        from app.subsystems.computer.domains.terminal import TERMINAL_DOMAIN
        from app.subsystems.computer.domains.clipboard import CLIPBOARD_DOMAIN
        from app.subsystems.computer.domains.app import APP_DOMAIN

        instances = {
            "UIAEngine": (UIA_ENGINE, IUIAEngine),
            "WindowDomain": (WINDOW_DOMAIN, IWindowDomain),
            "UIDomain": (UI_DOMAIN, IUIADomain),
            "BrowserDomain": (BROWSER_DOMAIN, IBrowserDomain),
            "WebDomain": (WEB_DOMAIN, IWebDomain),
            "KeyboardDomain": (KEYBOARD_DOMAIN, IKeyboardDomain),
            "MouseDomain": (MOUSE_DOMAIN, IMouseDomain),
            "ScreenDomain": (SCREEN_DOMAIN, IScreenDomain),
            "VisionDomain": (VISION_DOMAIN, IVisionDomain),
            "FilesystemDomain": (FILESYSTEM_DOMAIN, IFilesystemDomain),
            "TerminalDomain": (TERMINAL_DOMAIN, ITerminalDomain),
            "ClipboardDomain": (CLIPBOARD_DOMAIN, IClipboardDomain),
            "AppDomain": (APP_DOMAIN, IAppDomain),
        }

        registry = {}
        for engine_name, (inst, proto) in instances.items():
            registry[engine_name] = cls.verify_instance(inst, proto, engine_name)

        return {
            "status": "CONFORMANT",
            "total_engines": len(registry),
            "engines": registry,
        }


CONFORMANCE_VERIFIER = EngineConformanceVerifier
