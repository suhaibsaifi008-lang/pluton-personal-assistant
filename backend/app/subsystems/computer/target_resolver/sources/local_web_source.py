"""
Discovery Source for Local Web Applications & Dev Servers (Loopback Only)
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional
import httpx
from ..contracts import LocalServiceInfo, TargetCandidate, TargetType
from .base import DiscoverySource

logger = logging.getLogger("pluton.target_resolver.local_web")

COMMON_DEV_PORTS = (5173, 3000, 8000, 8080, 5000, 8081, 4000, 8888, 9000)


class LocalWebServiceDiscovery(DiscoverySource):
    """Discovers running local development web applications safely on 127.0.0.1 without hardcoded app names."""
    name = "local_web"

    def __init__(self, per_port_timeout: float = 0.20, aggregate_timeout: float = 0.50):
        self.per_port_timeout = per_port_timeout
        self.aggregate_timeout = aggregate_timeout

    def _get_active_listening_ports(self) -> list[int]:
        """Detect open TCP listening ports on 127.0.0.1 / localhost safely."""
        ports = set()
        try:
            import psutil
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN" and conn.laddr:
                    ip = conn.laddr.ip
                    port = conn.laddr.port
                    if ip in ("127.0.0.1", "0.0.0.0", "localhost", "::1") and 1024 <= port <= 65535:
                        ports.add(port)
        except Exception:
            pass

        # Fallback to common dev ports if psutil fails or has limited permissions
        for p in COMMON_DEV_PORTS:
            ports.add(p)

        return sorted(ports)

    async def _probe_port(self, client: httpx.AsyncClient, port: int) -> Optional[LocalServiceInfo]:
        """Probe loopback HTTP endpoint safely for HTML title and application metadata."""
        url = f"http://127.0.0.1:{port}"
        try:
            resp = await client.get(url, headers={"User-Agent": "PlutonDiscoveryBot/1.0"}, timeout=self.per_port_timeout)
            if resp.status_code < 400:
                body_chunk = resp.text[:4096]
                
                # 1. Extract HTML <title>
                title = None
                m_title = re.search(r"<title[^>]*>(.*?)</title>", body_chunk, flags=re.IGNORECASE | re.DOTALL)
                if m_title:
                    title = re.sub(r"\s+", " ", m_title.group(1)).strip()

                # 2. Extract <meta name="application-name" ...>
                app_name = None
                m_app = re.search(r'<meta[^>]+name=[\'"]application-name[\'"][^>]+content=[\'"](.*?)[\'"]', body_chunk, flags=re.IGNORECASE)
                if not m_app:
                    m_app = re.search(r'<meta[^>]+content=[\'"](.*?)[\'"][^>]+name=[\'"]application-name[\'"]', body_chunk, flags=re.IGNORECASE)
                if m_app:
                    app_name = m_app.group(1).strip()

                # 3. Extract prominent <h1> if title not found
                if not title:
                    m_h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body_chunk, flags=re.IGNORECASE | re.DOTALL)
                    if m_h1:
                        title = re.sub(r"<[^>]+>", "", m_h1.group(1)).strip()

                if title or app_name:
                    return LocalServiceInfo(
                        host="127.0.0.1",
                        port=port,
                        protocol="http",
                        title=title,
                        application_name=app_name,
                        url=url,
                    )
        except Exception:
            pass
        return None

    async def discover_services(self) -> list[LocalServiceInfo]:
        """Discover all active local web applications on loopback."""
        candidate_ports = self._get_active_listening_ports()
        services: list[LocalServiceInfo] = []

        async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
            tasks = [self._probe_port(client, p) for p in candidate_ports]
            try:
                done = await asyncio.gather(*tasks, return_exceptions=True)
                for res in done:
                    if isinstance(res, LocalServiceInfo) and res is not None:
                        services.append(res)
            except Exception as ex:
                logger.debug("[LOCAL_WEB_SOURCE] Discovery gather error: %s", ex)

        return services

    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        candidates: list[TargetCandidate] = []
        q_clean = query.strip().lower()
        if not q_clean:
            return candidates

        services = await self.discover_services()
        for s in services:
            title = s.title or ""
            app_name = s.application_name or ""
            text_corpus = f"{title} {app_name}".lower()

            if not text_corpus.strip():
                continue

            # Multi-token or exact substring match
            score = 0.0
            if q_clean in text_corpus:
                score = 0.92
            elif any(w in text_corpus for w in q_clean.split() if len(w) > 2):
                score = 0.80

            if score > 0.0:
                display_name = title or app_name or f"Local App (Port {s.port})"
                candidates.append(
                    TargetCandidate(
                        target_type=TargetType.LOCAL_WEB_SERVICE,
                        identity=s.url,
                        name=display_name,
                        source=self.name,
                        metadata={
                            "host": s.host,
                            "port": s.port,
                            "url": s.url,
                            "title": s.title,
                            "application_name": s.application_name,
                        },
                        score=score,
                        matched_tokens=tuple(q_clean.split()),
                    )
                )

        return candidates