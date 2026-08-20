"""
Discovery Source for Public Web Domains and Canonical URLs
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Optional
from ..contracts import TargetCandidate, TargetType
from .base import DiscoverySource

logger = logging.getLogger("pluton.target_resolver.domain")

_BRAND_DOMAINS = {
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
}


class PublicDomainSource(DiscoverySource):
    name = "domain"

    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        candidates: list[TargetCandidate] = []
        q = query.strip().strip('"\'')
        if not q:
            return candidates

        clean_token = q.lower().strip()

        # 1. Standard Brand Domains
        if clean_token in _BRAND_DOMAINS:
            url = _BRAND_DOMAINS[clean_token]
            parsed = urllib.parse.urlparse(url)
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.PUBLIC_WEB_DOMAIN,
                    identity=url,
                    name=clean_token.title(),
                    source=self.name,
                    metadata={"url": url, "netloc": parsed.netloc},
                    score=0.98,
                    matched_tokens=(clean_token,),
                )
            )
            return candidates

        # 2. Full explicit HTTP/HTTPS URL
        if q.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(q)
            netloc = parsed.netloc or q
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.PUBLIC_WEB_DOMAIN,
                    identity=q,
                    name=netloc,
                    source=self.name,
                    metadata={"url": q, "netloc": netloc},
                    score=1.0,
                    matched_tokens=(q,),
                )
            )
            return candidates

        # 3. Localhost / Explicit IP
        if q.startswith(("localhost", "127.0.0.1")):
            url = f"http://{q}"
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.LOCAL_WEB_SERVICE,
                    identity=url,
                    name=q,
                    source=self.name,
                    metadata={"url": url, "host": q.split(":")[0]},
                    score=0.98,
                    matched_tokens=(q,),
                )
            )
            return candidates

        # 4. Known TLD / Dot-Domain pattern (e.g. anker.com, hentaihaven.xxx, example.org, newsite.co.uk)
        tld_pattern = r"^[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)+(/.*)?$"
        if re.match(tld_pattern, q) and not q.endswith((".exe", ".txt", ".py", ".json", ".doc", ".pdf", ".lnk")):
            url = f"https://{q}"
            label = q.split("/")[0]
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.PUBLIC_WEB_DOMAIN,
                    identity=url,
                    name=label,
                    source=self.name,
                    metadata={"url": url, "netloc": label},
                    score=0.95,
                    matched_tokens=(q,),
                )
            )
            return candidates

        if "test page" in clean_token or "web interaction" in clean_token:
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.LOCAL_WEB_SERVICE,
                    identity="http://127.0.0.1:5173/test_page.html",
                    name="Pluton Test Page",
                    source=self.name,
                    metadata={"url": "http://127.0.0.1:5173/test_page.html"},
                    score=0.90,
                    matched_tokens=(clean_token,),
                )
            )
            return candidates

        # 5. Generic single-word web service / domain discovery (e.g. openai, huggingface, twitter, netflix)
        intent = getattr(context, "intent", None) or (context.get("intent") if isinstance(context, dict) else None)
        if re.match(r"^[a-zA-Z0-9\-]+$", clean_token) and len(clean_token) >= 3 and not clean_token.isdigit():
            domain_url = f"https://www.{clean_token}.com"
            # High score when explicit navigate intent, lower fallback score for generic open
            domain_score = 0.95 if intent == "navigate" else 0.70
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.PUBLIC_WEB_DOMAIN,
                    identity=domain_url,
                    name=clean_token.title(),
                    source=self.name,
                    metadata={"url": domain_url, "netloc": f"{clean_token}.com"},
                    score=domain_score,
                    matched_tokens=(clean_token,),
                )
            )

        return candidates