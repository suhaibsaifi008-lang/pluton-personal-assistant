"""
Abstract Base Class for Target Discovery Sources
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from ..contracts import TargetCandidate


class DiscoverySource(ABC):
    """Abstract interface for environment-based target discovery engines."""
    name: str

    @abstractmethod
    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        """Discover and return candidate targets matching query."""
        ...