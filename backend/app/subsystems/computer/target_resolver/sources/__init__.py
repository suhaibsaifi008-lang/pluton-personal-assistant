"""
Target Discovery Sources Package
"""

from .base import DiscoverySource
from .window_source import WindowDiscoverySource
from .browser_tab_source import BrowserTabDiscoverySource
from .local_web_source import LocalWebServiceDiscovery
from .desktop_app_source import DesktopAppDiscoverySource
from .domain_source import PublicDomainSource
from .filesystem_source import FilesystemDiscoverySource

__all__ = [
    "DiscoverySource",
    "WindowDiscoverySource",
    "BrowserTabDiscoverySource",
    "LocalWebServiceDiscovery",
    "DesktopAppDiscoverySource",
    "PublicDomainSource",
    "FilesystemDiscoverySource",
]