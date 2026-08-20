"""
Discovery Source for Filesystem Targets
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional
from ..contracts import TargetCandidate, TargetType
from .base import DiscoverySource

logger = logging.getLogger("pluton.target_resolver.filesystem")


class FilesystemDiscoverySource(DiscoverySource):
    name = "filesystem"

    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        candidates: list[TargetCandidate] = []
        q = query.strip().strip('"\'')
        if not q:
            return candidates

        try:
            # Check direct path
            p = Path(os.path.expanduser(q))
            if p.exists():
                candidates.append(
                    TargetCandidate(
                        target_type=TargetType.FILESYSTEM_PATH,
                        identity=str(p.resolve()),
                        name=p.name,
                        source=self.name,
                        metadata={"path": str(p.resolve()), "is_dir": p.is_dir()},
                        score=0.95,
                        matched_tokens=(q,),
                    )
                )
        except Exception:
            pass

        return candidates