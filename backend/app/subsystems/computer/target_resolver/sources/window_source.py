"""
Discovery Source for Active Desktop Windows
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from ..contracts import TargetCandidate, TargetType
from .base import DiscoverySource

logger = logging.getLogger("pluton.target_resolver.window")


class WindowDiscoverySource(DiscoverySource):
    name = "window"

    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        candidates: list[TargetCandidate] = []
        q_clean = str(query or "").strip().lower()
        if not q_clean:
            return candidates

        try:
            from app.tools.uia_engine import UIA_ENGINE
            windows = UIA_ENGINE.list_windows(visible_only=True)
            for win in windows:
                title = str(win.get("title") or "").strip()
                hwnd = win.get("hwnd")
                pid = win.get("pid")
                class_name = str(win.get("class_name") or "").strip()
                if not hwnd:
                    continue

                title_lower = title.lower()
                is_explorer_class = class_name in ("CabinetWClass", "ExploreWClass", "XamlExplorerHostIslandWindow")
                is_explorer_query = q_clean in ("file explorer", "explorer", "folder", "files")

                # Match by title or by Explorer class
                if is_explorer_query and is_explorer_class:
                    candidates.append(
                        TargetCandidate(
                            target_type=TargetType.EXISTING_WINDOW,
                            identity=f"HWND:{hwnd}",
                            name=title or "File Explorer",
                            source=self.name,
                            metadata={"hwnd": hwnd, "pid": pid, "title": title or "File Explorer", "class_name": class_name},
                            score=0.96,
                            matched_tokens=(q_clean,),
                        )
                    )
                elif title and (q_clean == title_lower or q_clean in title_lower or title_lower in q_clean):
                    score = 0.95 if q_clean == title_lower else 0.80
                    candidates.append(
                        TargetCandidate(
                            target_type=TargetType.EXISTING_WINDOW,
                            identity=f"HWND:{hwnd}",
                            name=title,
                            source=self.name,
                            metadata={"hwnd": hwnd, "pid": pid, "title": title, "class_name": class_name},
                            score=score,
                            matched_tokens=(q_clean,),
                        )
                    )
        except Exception as ex:
            logger.debug("[WINDOW_SOURCE] Non-critical error listing windows: %s", ex)

        return candidates