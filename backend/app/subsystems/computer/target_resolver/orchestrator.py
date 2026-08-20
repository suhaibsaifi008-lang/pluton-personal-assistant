"""
Target Resolution Orchestrator
Coordinates multi-source candidate discovery, scoring, and legacy interface conformance.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Optional

from ..contracts import (
    ComputerDomain,
    ResolvedTarget,
    TargetResolutionStatus,
    TargetSpec,
)
from .contracts import (
    TargetCandidate,
    TargetResolutionResult,
    TargetType,
)
from .scorer import CandidateScorer
from .sources import (
    BrowserTabDiscoverySource,
    DesktopAppDiscoverySource,
    DiscoverySource,
    FilesystemDiscoverySource,
    LocalWebServiceDiscovery,
    PublicDomainSource,
    WindowDiscoverySource,
)

logger = logging.getLogger("pluton.target_resolver.orchestrator")


class TargetResolver:
    """Canonical evidence-based Target Resolver."""

    def __init__(
        self,
        uia_engine: Any = None,
        browser_engine: Any = None,
        sources: Optional[list[DiscoverySource]] = None,
    ) -> None:
        self._uia = uia_engine
        self._browser = browser_engine
        self.sources = sources or [
            WindowDiscoverySource(),
            BrowserTabDiscoverySource(),
            LocalWebServiceDiscovery(),
            DesktopAppDiscoverySource(),
            PublicDomainSource(),
            FilesystemDiscoverySource(),
        ]

    @property
    def uia(self) -> Any:
        if self._uia is None:
            from app.tools.uia_engine import UIA_ENGINE
            self._uia = UIA_ENGINE
        return self._uia

    @property
    def browser(self) -> Any:
        if self._browser is None:
            from ..browser_engine import BROWSER_ENGINE
            self._browser = BROWSER_ENGINE
        return self._browser

    # -------------------------------------------------------------------------
    # Core Generic Resolution Pipeline
    # -------------------------------------------------------------------------

    def resolve_target(
        self,
        query: str,
        intent: str = "open",
        context: Optional[Any] = None,
    ) -> TargetResolutionResult:
        """Synchronous target resolution wrapper running async discover across sources."""
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.resolve_query(query, intent, context))
                    try:
                        return future.result(timeout=3.0)
                    except concurrent.futures.TimeoutError:
                        logger.warning("[TARGET_RESOLVER] resolve_target timed out for query='%s'", query)
                        return TargetResolutionResult(
                            status=TargetResolutionStatus.TARGET_NOT_FOUND,
                            reason=f"TARGET_NOT_FOUND: Resolution timed out for '{query}'.",
                        )
            else:
                return asyncio.run(self.resolve_query(query, intent, context))
        except Exception as ex:
            logger.error("[TARGET_RESOLVER] resolve_target error for query='%s': %s", query, ex, exc_info=True)
            return TargetResolutionResult(
                status=TargetResolutionStatus.TARGET_NOT_FOUND,
                reason=f"TARGET_NOT_FOUND: Resolution exception {ex}",
            )

    async def resolve_query(
        self,
        query: str,
        intent: str = "open",
        context: Optional[Any] = None,
    ) -> TargetResolutionResult:
        """Resolve a natural target query across all live environment discovery sources."""
        q_clean = query.strip()
        if not q_clean:
            return TargetResolutionResult(
                status=TargetResolutionStatus.TARGET_NOT_FOUND,
                reason="Empty target query.",
            )

        # 1. Candidate Discovery across all sources concurrently
        tasks = [src.discover_candidates(q_clean, context) for src in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: list[TargetCandidate] = []
        for i, r in enumerate(results):
            if isinstance(r, list):
                all_candidates.extend(r)
            elif isinstance(r, Exception):
                src_name = self.sources[i].name if i < len(self.sources) else f"source_{i}"
                logger.warning("[TARGET_RESOLVER] Discovery source '%s' raised exception: %s", src_name, r)

        if not all_candidates:
            return TargetResolutionResult(
                status=TargetResolutionStatus.TARGET_NOT_FOUND,
                reason=f"TARGET_NOT_FOUND: No local application, window, tab, or domain matched '{q_clean}'.",
            )

        # 2. Multi-Signal Candidate Ranking
        ranked = CandidateScorer.rank_candidates(all_candidates, q_clean, intent=intent)

        # 3. Ambiguity Gating
        is_ambig, ambig_reason = CandidateScorer.check_ambiguity(ranked)
        if is_ambig:
            return TargetResolutionResult(
                status=TargetResolutionStatus.AMBIGUOUS_TARGET,
                all_candidates=tuple(ranked),
                is_ambiguous=True,
                refusal_reason=ambig_reason,
                reason=ambig_reason or "AMBIGUOUS_TARGET",
            )

        top = ranked[0]
        if top.score < 0.65:
            return TargetResolutionResult(
                status=TargetResolutionStatus.TARGET_NOT_FOUND,
                all_candidates=tuple(ranked),
                reason=f"TARGET_NOT_FOUND: Low confidence match for '{q_clean}'.",
            )

        # 4. Map TargetCandidate to ResolvedTarget and Recommended Capability
        resolved_domain = ComputerDomain.APP
        recommended_cap = "app.launch"
        bound_params: dict[str, Any] = {}

        if top.target_type == TargetType.EXISTING_WINDOW:
            resolved_domain = ComputerDomain.WINDOW
            recommended_cap = "window.focus"
            bound_params = {"hwnd": top.metadata.get("hwnd"), "title": top.name}
        elif top.target_type == TargetType.EXISTING_BROWSER_TAB:
            resolved_domain = ComputerDomain.BROWSER
            recommended_cap = "browser.switch_tab"
            bound_params = {"target": top.name, "browser": top.metadata.get("browser", "Brave"), "url": top.metadata.get("url")}
        elif top.target_type == TargetType.LOCAL_WEB_SERVICE:
            resolved_domain = ComputerDomain.WEB
            recommended_cap = "browser.navigate"
            bound_params = {"url": top.identity, "browser": getattr(context, "active_browser", "Brave")}
        elif top.target_type == TargetType.PUBLIC_WEB_DOMAIN:
            resolved_domain = ComputerDomain.WEB
            recommended_cap = "browser.navigate"
            bound_params = {"url": top.identity, "browser": getattr(context, "active_browser", "Brave")}
        elif top.target_type == TargetType.INSTALLED_DESKTOP_APP:
            resolved_domain = ComputerDomain.APP
            recommended_cap = "app.launch"
            bound_params = {"app_name": top.name.lower(), "exe": top.identity, "args": top.metadata.get("args")}
        elif top.target_type == TargetType.FILESYSTEM_PATH:
            resolved_domain = ComputerDomain.FILESYSTEM
            recommended_cap = "filesystem.read"
            bound_params = {"path": top.identity}

        resolved_target = ResolvedTarget(
            target_id=f"target_{top.target_type.value}_{top.name}",
            name=top.name,
            domain=resolved_domain,
            hwnd=top.metadata.get("hwnd"),
            pid=top.metadata.get("pid"),
            url=top.metadata.get("url") or (top.identity if top.target_type in (TargetType.LOCAL_WEB_SERVICE, TargetType.PUBLIC_WEB_DOMAIN) else None),
            confidence=top.score,
            metadata=top.metadata,
        )

        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=resolved_target,
            selected_candidate=top,
            all_candidates=tuple(ranked),
            recommended_capability=recommended_cap,
            bound_action_params=bound_params,
            reason="RESOLVED",
        )

    # -------------------------------------------------------------------------
    # Legacy Synchronous Resolve Facade (100% Backward Compatibility)
    # -------------------------------------------------------------------------

    def resolve(self, domain: ComputerDomain | TargetSpec, spec: TargetSpec | ComputerDomain | None = None) -> TargetResolutionResult:
        """Synchronous domain-specific resolution for existing computer domain tests."""
        if isinstance(domain, TargetSpec):
            if isinstance(spec, ComputerDomain):
                domain, spec = spec, domain
            else:
                domain, spec = ComputerDomain.UI, domain

        if domain == ComputerDomain.WINDOW:
            return self._resolve_window(spec)
        elif domain == ComputerDomain.BROWSER:
            return self._resolve_browser_tab(spec)
        elif domain == ComputerDomain.WEB:
            return self._resolve_web_target(spec)
        elif domain == ComputerDomain.UI:
            return self._resolve_ui_element(spec)
        elif domain == ComputerDomain.APP:
            return self._resolve_app(spec)
        elif domain == ComputerDomain.FILESYSTEM:
            return self._resolve_filesystem(spec)
        elif domain == ComputerDomain.TERMINAL:
            return self._resolve_terminal(spec)
        else:
            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=ResolvedTarget(
                    target_id=f"target_{domain.value}",
                    name=spec.semantic_name or spec.raw_query or domain.value,
                    domain=domain,
                    metadata=spec.attributes,
                ),
            )

    def _resolve_window(self, spec: TargetSpec) -> TargetResolutionResult:
        if spec.hwnd and spec.hwnd > 0:
            import ctypes
            if bool(ctypes.windll.user32.IsWindow(spec.hwnd)):
                return TargetResolutionResult(
                    status=TargetResolutionStatus.RESOLVED,
                    target=ResolvedTarget(
                        target_id=f"hwnd_{spec.hwnd}",
                        name=spec.semantic_name or f"Window_{spec.hwnd}",
                        domain=ComputerDomain.WINDOW,
                        hwnd=spec.hwnd,
                        pid=spec.pid,
                    ),
                )
            return TargetResolutionResult(
                status=TargetResolutionStatus.STALE_TARGET,
                reason=f"Window HWND {spec.hwnd} is not a valid or live window.",
            )

        title_q = (spec.semantic_name or spec.exact_text or spec.raw_query or "").strip().lower()
        if not title_q:
            return TargetResolutionResult(status=TargetResolutionStatus.INVALID_TARGET, reason="No window title provided.")

        try:
            wins = self.uia.list_windows(visible_only=True)
            matched = [w for w in wins if title_q in (w.get("title") or "").lower()]
            if len(matched) == 1:
                w = matched[0]
                return TargetResolutionResult(
                    status=TargetResolutionStatus.RESOLVED,
                    target=ResolvedTarget(
                        target_id=f"hwnd_{w['hwnd']}",
                        name=w.get("title", ""),
                        domain=ComputerDomain.WINDOW,
                        hwnd=w.get("hwnd"),
                        pid=w.get("pid"),
                    ),
                )
            elif len(matched) > 1:
                candidates = [
                    ResolvedTarget(
                        target_id=f"hwnd_{w['hwnd']}",
                        name=w.get("title", ""),
                        domain=ComputerDomain.WINDOW,
                        hwnd=w.get("hwnd"),
                        pid=w.get("pid"),
                    )
                    for w in matched
                ]
                return TargetResolutionResult(
                    status=TargetResolutionStatus.AMBIGUOUS_TARGET,
                    candidates=candidates,
                    reason=f"Found {len(matched)} matching windows.",
                )
        except Exception:
            pass

        return TargetResolutionResult(status=TargetResolutionStatus.TARGET_NOT_FOUND, reason="Window not found.")

    def _resolve_browser_tab(self, spec: TargetSpec) -> TargetResolutionResult:
        tab_q = (spec.tab_title or spec.semantic_name or spec.raw_query or "").strip().lower()
        bname = spec.browser_name or "Brave"
        try:
            from app.tools.native_browser_controller import NATIVE_BROWSER
            tabs = NATIVE_BROWSER.list_tabs(bname)
            matched = [t for t in tabs if tab_q in (t.get("title") or "").lower() or (t.get("url") and tab_q in t["url"].lower())]
            if len(matched) == 1:
                t = matched[0]
                return TargetResolutionResult(
                    status=TargetResolutionStatus.RESOLVED,
                    target=ResolvedTarget(
                        target_id=f"tab_{t.get('id')}",
                        name=t.get("title", ""),
                        domain=ComputerDomain.BROWSER,
                        hwnd=t.get("hwnd"),
                        url=t.get("url"),
                    ),
                )
            elif len(matched) > 1:
                candidates = [
                    ResolvedTarget(
                        target_id=f"tab_{t.get('id')}",
                        name=t.get("title", ""),
                        domain=ComputerDomain.BROWSER,
                        hwnd=t.get("hwnd"),
                        url=t.get("url"),
                    )
                    for t in matched
                ]
                return TargetResolutionResult(
                    status=TargetResolutionStatus.AMBIGUOUS_TARGET,
                    candidates=candidates,
                    reason=f"Found {len(matched)} matching tabs in {bname}.",
                )
        except Exception:
            pass
        return TargetResolutionResult(status=TargetResolutionStatus.TARGET_NOT_FOUND, reason=f"Tab '{tab_q}' not found.")

    def _resolve_web_target(self, spec: TargetSpec) -> TargetResolutionResult:
        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=ResolvedTarget(
                target_id="web_target",
                name=spec.semantic_name or "web_element",
                domain=ComputerDomain.WEB,
                metadata={"selector": spec.dom_selector, "text": spec.exact_text},
            ),
        )

    def _resolve_ui_element(self, spec: TargetSpec) -> TargetResolutionResult:
        query_text = (spec.semantic_name or spec.exact_text or spec.raw_query or "").strip()
        ctrl_type = (spec.control_type or "").strip().lower()

        if hasattr(self.uia, "find_elements_by_query"):
            try:
                elements = self.uia.find_elements_by_query(query=query_text, hwnd=spec.hwnd)
                if elements:
                    if ctrl_type:
                        filtered = [el for el in elements if ctrl_type in (el.get("control_type") or "").lower()]
                        if filtered:
                            elements = filtered

                    best = elements[0]
                    return TargetResolutionResult(
                        status=TargetResolutionStatus.RESOLVED,
                        target=ResolvedTarget(
                            target_id=best.get("automation_id") or "ui_element",
                            name=best.get("name") or query_text,
                            domain=ComputerDomain.UI,
                            automation_id=best.get("automation_id"),
                            control_type=best.get("control_type") or spec.control_type,
                            bounds=best.get("bounding_rectangle"),
                        ),
                    )
            except Exception:
                pass

        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=ResolvedTarget(
                target_id="ui_element",
                name=query_text or "control",
                domain=ComputerDomain.UI,
                automation_id=spec.automation_id,
                control_type=spec.control_type,
            ),
        )

    def _resolve_app(self, spec: TargetSpec) -> TargetResolutionResult:
        app_q = (spec.app_identity or spec.semantic_name or spec.raw_query or "").strip().lower()
        if not app_q:
            return TargetResolutionResult(status=TargetResolutionStatus.TARGET_NOT_FOUND, reason="Empty application query.")

        from app.planning.intent_compiler import UniversalAppRegistry
        meta = UniversalAppRegistry.resolve(app_q)
        if meta and meta.get("exe"):
            canonical_name = meta.get("canonical_name", app_q.capitalize())
            return TargetResolutionResult(
                status=TargetResolutionStatus.RESOLVED,
                target=ResolvedTarget(
                    target_id=f"app_{canonical_name.lower()}",
                    name=canonical_name,
                    domain=ComputerDomain.APP,
                    metadata=meta,
                ),
            )
        return TargetResolutionResult(status=TargetResolutionStatus.TARGET_NOT_FOUND, reason=f"App '{app_q}' not found.")

    def _resolve_filesystem(self, spec: TargetSpec) -> TargetResolutionResult:
        p = spec.raw_query or spec.semantic_name or ""
        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=ResolvedTarget(
                target_id=f"file_{p}",
                name=p,
                domain=ComputerDomain.FILESYSTEM,
                metadata={"path": p},
            ),
        )

    def _resolve_terminal(self, spec: TargetSpec) -> TargetResolutionResult:
        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=ResolvedTarget(
                target_id="terminal",
                name="terminal",
                domain=ComputerDomain.TERMINAL,
            ),
        )


TARGET_RESOLVER = TargetResolver()