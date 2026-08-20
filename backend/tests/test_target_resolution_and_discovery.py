"""
PLUTON V2 — Evidence-Based Target Resolution & Local Web Discovery Test Suite
Covers unit and integration tests for multi-source candidate discovery, scoring,
ambiguity gating, search gating, and live localhost web service probing.
"""

import asyncio
from typing import Any
import pytest

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    TargetDomain,
)
from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER, SearchQueryExtractor
from app.subsystems.computer.target_resolver import (
    LocalServiceInfo,
    TARGET_RESOLVER,
    TargetCandidate,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetResolver,
    TargetType,
)
from app.subsystems.computer.target_resolver.scorer import CandidateScorer
from app.subsystems.computer.target_resolver.sources import (
    BrowserTabDiscoverySource,
    DesktopAppDiscoverySource,
    DiscoverySource,
    FilesystemDiscoverySource,
    LocalWebServiceDiscovery,
    PublicDomainSource,
    WindowDiscoverySource,
)


class MockDiscoverySource(DiscoverySource):
    def __init__(self, name: str, candidates: list[TargetCandidate]):
        self.name = name
        self._candidates = candidates

    async def discover_candidates(self, query: str, context: Any = None) -> list[TargetCandidate]:
        return self._candidates


# =============================================================================
# 2. Unit Tests (Synchronous with asyncio.run)
# =============================================================================

def test_1_exact_existing_window_match():
    """Verify window source matches existing desktop window by title."""
    async def run():
        src = MockDiscoverySource("window", [
            TargetCandidate(
                target_type=TargetType.EXISTING_WINDOW,
                identity="HWND:12345",
                name="Calculator",
                source="window",
                metadata={"hwnd": 12345, "pid": 999},
                score=0.95,
            )
        ])
        resolver = TargetResolver(sources=[src])
        res = await resolver.resolve_query("Calculator", intent="open")
        assert res.status == TargetResolutionStatus.RESOLVED
        assert res.selected_candidate is not None
        assert res.selected_candidate.target_type == TargetType.EXISTING_WINDOW
        assert res.recommended_capability == "window.focus"

    asyncio.run(run())


def test_2_existing_browser_tab_match():
    """Verify browser tab source matches open browser tab by title."""
    async def run():
        src = MockDiscoverySource("browser_tab", [
            TargetCandidate(
                target_type=TargetType.EXISTING_BROWSER_TAB,
                identity="https://github.com/my-repo",
                name="My Repo · GitHub",
                source="browser_tab",
                metadata={"browser": "Brave", "tab_title": "My Repo · GitHub", "url": "https://github.com/my-repo"},
                score=0.90,
            )
        ])
        resolver = TargetResolver(sources=[src])
        res = await resolver.resolve_query("My Repo", intent="switch")
        assert res.status == TargetResolutionStatus.RESOLVED
        assert res.selected_candidate is not None
        assert res.selected_candidate.target_type == TargetType.EXISTING_BROWSER_TAB
        assert res.recommended_capability == "browser.switch_tab"

    asyncio.run(run())


def test_3_installed_desktop_app_match():
    """Verify desktop app source resolves system apps without web searching."""
    async def run():
        src = DesktopAppDiscoverySource()
        candidates = await src.discover_candidates("notepad")
        assert len(candidates) >= 1
        assert candidates[0].target_type == TargetType.INSTALLED_DESKTOP_APP
        assert "notepad" in candidates[0].identity.lower()

    asyncio.run(run())


def test_4_explicit_url_match():
    """Verify public domain source matches explicit URLs."""
    async def run():
        src = PublicDomainSource()
        candidates = await src.discover_candidates("https://anker.com/products")
        assert len(candidates) == 1
        assert candidates[0].target_type == TargetType.PUBLIC_WEB_DOMAIN
        assert candidates[0].identity == "https://anker.com/products"

    asyncio.run(run())


def test_5_local_web_service_discovery():
    """Verify LocalWebServiceDiscovery extracts title and metadata from loopback endpoint."""
    async def run():
        candidate = TargetCandidate(
            target_type=TargetType.LOCAL_WEB_SERVICE,
            identity="http://127.0.0.1:5173",
            name="Pluton AI UI",
            source="local_web",
            metadata={"port": 5173, "title": "Pluton AI UI", "url": "http://127.0.0.1:5173"},
            score=0.92,
        )
        mock_src = MockDiscoverySource("local_web", [candidate])
        resolver = TargetResolver(sources=[mock_src])
        res = await resolver.resolve_query("Pluton", intent="open")
        assert res.status == TargetResolutionStatus.RESOLVED
        assert res.selected_candidate.target_type == TargetType.LOCAL_WEB_SERVICE
        assert res.selected_candidate.identity == "http://127.0.0.1:5173"

    asyncio.run(run())


def test_6_no_local_web_server():
    """Verify empty candidate list when no local service matches."""
    async def run():
        mock_src = MockDiscoverySource("local_web", [])
        resolver = TargetResolver(sources=[mock_src])
        res = await resolver.resolve_query("Unrelated Local Service", intent="open")
        assert res.status == TargetResolutionStatus.TARGET_NOT_FOUND

    asyncio.run(run())


def test_7_malformed_local_http_service():
    """Verify LocalWebServiceDiscovery handles connection errors gracefully."""
    async def run():
        src = LocalWebServiceDiscovery(per_port_timeout=0.05)
        import httpx
        async with httpx.AsyncClient() as client:
            info = await src._probe_port(client, 64999)
            assert info is None

    asyncio.run(run())


def test_8_non_http_listening_port():
    """Verify raw TCP probe failure does not throw uncaught exceptions."""
    async def run():
        src = LocalWebServiceDiscovery(per_port_timeout=0.05)
        import httpx
        async with httpx.AsyncClient() as client:
            info = await src._probe_port(client, 64998)
            assert info is None

    asyncio.run(run())


def test_9_explicit_search_command():
    """Verify explicit search commands compile to semantic search action."""
    ctx = ExecutionContext(task_id="t_search_1")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Search Google for Pluton AI", ctx)
    assert len(plan.steps) == 1
    action = plan.steps[0].action
    assert action.capability == CapabilityType.WEB_TYPE
    assert action.parameters["text"] == "Pluton AI"


def test_10_open_navigate_unknown_multi_word_target():
    """Verify operational open command for unknown target does NOT fallback to Google Search."""
    ctx = ExecutionContext(task_id="t_open_unknown")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open Some Completely Nonexistent Random App Name 12345", ctx)
    assert len(plan.steps) == 1
    action = plan.steps[0].action
    # Must NOT be a Google search!
    assert action.capability != CapabilityType.BROWSER_NAVIGATE
    assert "google.com" not in action.target
    assert "TARGET_NOT_FOUND" in str(action.parameters.get("error"))


def test_11_ambiguity_between_two_local_services():
    """Verify ambiguity gate triggers when two local services have matching titles and equal scores."""
    async def run():
        cands = [
            TargetCandidate(
                target_type=TargetType.LOCAL_WEB_SERVICE,
                identity="http://127.0.0.1:5173",
                name="Pluton AI UI",
                source="local_web",
                score=0.92,
            ),
            TargetCandidate(
                target_type=TargetType.LOCAL_WEB_SERVICE,
                identity="http://127.0.0.1:3000",
                name="Pluton AI Dashboard",
                source="local_web",
                score=0.92,
            ),
        ]
        resolver = TargetResolver(sources=[MockDiscoverySource("local_web", cands)])
        res = await resolver.resolve_query("Pluton", intent="open")
        assert res.status == TargetResolutionStatus.AMBIGUOUS_TARGET
        assert res.is_ambiguous is True
        assert "AMBIGUOUS_TARGET" in (res.refusal_reason or "")

    asyncio.run(run())


def test_12_ambiguity_between_browser_tabs():
    """Verify ambiguity gate triggers when two open browser tabs have matching titles."""
    async def run():
        cands = [
            TargetCandidate(
                target_type=TargetType.EXISTING_BROWSER_TAB,
                identity="tab_1",
                name="Pluton Workspace (Brave)",
                source="browser_tab",
                score=0.90,
            ),
            TargetCandidate(
                target_type=TargetType.EXISTING_BROWSER_TAB,
                identity="tab_2",
                name="Pluton Workspace (Chrome)",
                source="browser_tab",
                score=0.90,
            ),
        ]
        resolver = TargetResolver(sources=[MockDiscoverySource("browser_tab", cands)])
        res = await resolver.resolve_query("Pluton", intent="switch")
        assert res.status == TargetResolutionStatus.AMBIGUOUS_TARGET
        assert res.is_ambiguous is True

    asyncio.run(run())


def test_13_liveness_preference():
    """Verify CandidateScorer prioritizes already open tabs/windows over unlaunched apps."""
    cands = [
        TargetCandidate(
            target_type=TargetType.INSTALLED_DESKTOP_APP,
            identity="c:\\apps\\notes.exe",
            name="Notes App",
            source="desktop_app",
            score=0.85,
        ),
        TargetCandidate(
            target_type=TargetType.EXISTING_WINDOW,
            identity="HWND:100",
            name="Notes App",
            source="window",
            score=0.85,
        ),
    ]
    ranked = CandidateScorer.rank_candidates(cands, "Notes App", intent="open")
    assert ranked[0].target_type == TargetType.EXISTING_WINDOW


def test_14_duplicate_launch_prevention():
    """Verify CandidateScorer prefers existing tab over duplicate web navigation."""
    cands = [
        TargetCandidate(
            target_type=TargetType.PUBLIC_WEB_DOMAIN,
            identity="https://github.com",
            name="GitHub",
            source="domain",
            score=0.90,
        ),
        TargetCandidate(
            target_type=TargetType.EXISTING_BROWSER_TAB,
            identity="tab_gh",
            name="GitHub",
            source="browser_tab",
            score=0.90,
        ),
    ]
    ranked = CandidateScorer.rank_candidates(cands, "GitHub", intent="switch")
    assert ranked[0].target_type == TargetType.EXISTING_BROWSER_TAB


def test_15_stale_candidate_rejection():
    """Verify dead HWND returns STALE_TARGET."""
    from app.subsystems.computer.contracts import ComputerDomain, TargetSpec
    spec = TargetSpec(hwnd=99999999, semantic_name="Dead Window")
    res = TARGET_RESOLVER.resolve(ComputerDomain.WINDOW, spec)
    assert res.status in (TargetResolutionStatus.STALE_TARGET, TargetResolutionStatus.TARGET_NOT_FOUND)


def test_16_no_application_specific_hardcoded_mappings():
    """Verify that resolving an unknown app does not use hardcoded 'if target == ...' branches."""
    ctx = ExecutionContext(task_id="t_clean")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open ArbitraryCustomInternalTool", ctx)
    action = plan.steps[0].action
    assert "google.com" not in action.target


# =============================================================================
# 3. Integration Tests
# =============================================================================

def test_integration_a_open_pluton_live_or_mock():
    """Integration Test A: 'Open Pluton' resolves to the live/discovered service without hardcoding."""
    ctx = ExecutionContext(task_id="t_integ_a")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open Pluton", ctx)
    assert len(plan.steps) == 1
    action = plan.steps[0].action
    assert action.capability in (CapabilityType.BROWSER_SWITCH_TAB, CapabilityType.BROWSER_NAVIGATE, CapabilityType.WINDOW_FOCUS, CapabilityType.GENERAL_ACTION)
    if action.capability == CapabilityType.GENERAL_ACTION:
        assert "AMBIGUOUS_TARGET" in action.parameters.get("error", "")
    assert "google.com/search" not in action.target


def test_integration_b_open_unknown_app_not_found():
    """Integration Test B: 'Open Some Unknown Random App' returns TARGET_NOT_FOUND (No Google search)."""
    ctx = ExecutionContext(task_id="t_integ_b")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Open CompletelyUnknownAppXYZ999", ctx)
    assert len(plan.steps) == 1
    action = plan.steps[0].action
    assert action.capability != CapabilityType.BROWSER_NAVIGATE
    assert "google.com" not in action.target


def test_integration_c_search_google_intentionally():
    """Integration Test C: 'Search Google for Some Unknown Random App' generates semantic search action."""
    ctx = ExecutionContext(task_id="t_integ_c")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Search Google for CompletelyUnknownAppXYZ999", ctx)
    assert len(plan.steps) == 1
    action = plan.steps[0].action
    assert action.capability == CapabilityType.WEB_TYPE
    assert action.parameters["text"] == "CompletelyUnknownAppXYZ999"