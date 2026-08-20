"""
Discovery Source for Live Browser Tabs
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from ..contracts import TargetCandidate, TargetType
from .base import DiscoverySource

logger = logging.getLogger("pluton.target_resolver.browser_tab")


class BrowserTabDiscoverySource(DiscoverySource):
    name = "browser_tab"

    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        candidates: list[TargetCandidate] = []
        q_clean = query.strip().lower()
        if not q_clean:
            return candidates

        try:
            from app.tools.native_browser_controller import NATIVE_BROWSER
            active_browsers = ["Brave", "Chrome", "Edge"]
            for bname in active_browsers:
                tabs = NATIVE_BROWSER.list_tabs(bname)
                for tab in tabs:
                    title = (tab.get("title") or "").strip()
                    url = tab.get("url") or ""
                    hwnd = tab.get("hwnd")
                    if not title and not url:
                        continue

                    title_lower = title.lower()
                    url_lower = url.lower()
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(url_lower)
                    netloc = parsed_url.netloc

                    # Exclude specialized subdomains from generic parent brand queries
                    # e.g. "google" should NOT match "mail.google.com" (Gmail) or "docs.google.com"
                    is_subdomain_conflict = (
                        q_clean == "google" and any(sub in netloc for sub in ("mail.", "docs.", "drive.", "meet.", "calendar."))
                    )
                    if is_subdomain_conflict:
                        continue

                    # Exact title or netloc match
                    if q_clean == title_lower or q_clean == netloc or f"www.{q_clean}.com" == netloc:
                        score = 0.95
                    elif q_clean in title_lower:
                        score = 0.85
                    elif q_clean in netloc:
                        score = 0.80
                    else:
                        continue

                    candidates.append(
                        TargetCandidate(
                            target_type=TargetType.EXISTING_BROWSER_TAB,
                            identity=url or title,
                            name=title or url,
                            source=self.name,
                            metadata={
                                "browser": bname,
                                "tab_title": title,
                                "url": url,
                                "hwnd": hwnd,
                                "tab_id": tab.get("id"),
                            },
                            score=score,
                            matched_tokens=(q_clean,),
                        )
                    )
        except Exception as ex:
            logger.debug("[BROWSER_TAB_SOURCE] Non-critical error listing tabs: %s", ex)

        return candidates