"""
Multi-Signal Candidate Scorer and Ambiguity Gate
"""

from __future__ import annotations

import logging
from typing import Optional
from .contracts import TargetCandidate, TargetType

logger = logging.getLogger("pluton.target_resolver.scorer")


class CandidateScorer:
    """Ranks discovered target candidates and enforces ambiguity gating."""

    @staticmethod
    def rank_candidates(candidates: list[TargetCandidate], query: str, intent: str = "open") -> list[TargetCandidate]:
        """Rank candidates using multiple orthogonal signals."""
        if not candidates:
            return []

        q_lower = query.strip().lower()
        q_tokens = [w for w in q_lower.split() if len(w) > 0]
        scored: list[TargetCandidate] = []

        for cand in candidates:
            base_score = cand.score
            cand_name_lower = cand.name.lower()
            cand_tokens = [w for w in cand_name_lower.split() if len(w) > 0]

            # 1. Exact Name / Identity Match Boost
            if q_lower == cand_name_lower or q_lower == cand.identity.lower():
                base_score += 0.15
            elif cand_tokens and q_tokens:
                # Token coverage ratio (penalizes incidental matches in very long titles)
                matched_count = len([w for w in q_tokens if w in cand_tokens])
                coverage = matched_count / max(len(cand_tokens), len(q_tokens))
                base_score += coverage * 0.12

            # 2. Liveness / Open State Boost
            if cand.target_type == TargetType.EXISTING_BROWSER_TAB:
                base_score += 0.08
            elif cand.target_type == TargetType.EXISTING_WINDOW:
                base_score += 0.07
            elif cand.target_type == TargetType.LOCAL_WEB_SERVICE:
                base_score += 0.03

            # 3. Intent Verb Alignment
            if intent in ("switch", "focus") and cand.target_type in (TargetType.EXISTING_BROWSER_TAB, TargetType.EXISTING_WINDOW):
                base_score += 0.10
            elif intent in ("navigate", "browse") and cand.target_type in (TargetType.PUBLIC_WEB_DOMAIN, TargetType.LOCAL_WEB_SERVICE):
                base_score += 0.12
            elif intent in ("launch", "start") and cand.target_type == TargetType.INSTALLED_DESKTOP_APP:
                base_score += 0.05

            scored.append(
                TargetCandidate(
                    target_type=cand.target_type,
                    identity=cand.identity,
                    name=cand.name,
                    source=cand.source,
                    metadata=cand.metadata,
                    score=base_score,
                    matched_tokens=cand.matched_tokens,
                )
            )

        # Sort descending by score
        scored.sort(key=lambda c: c.score, reverse=True)

        # Normalize scores to [0.0, 1.0] for output contract
        normalized: list[TargetCandidate] = []
        for c in scored:
            normalized.append(
                TargetCandidate(
                    target_type=c.target_type,
                    identity=c.identity,
                    name=c.name,
                    source=c.source,
                    metadata=c.metadata,
                    score=min(1.0, max(0.0, c.score)),
                    matched_tokens=c.matched_tokens,
                )
            )

        return normalized

    @staticmethod
    def check_ambiguity(ranked: list[TargetCandidate], threshold_diff: float = 0.04) -> tuple[bool, Optional[str]]:
        """Determine if top candidates are too close in score to decide unambiguously."""
        if len(ranked) < 2:
            return False, None

        top1 = ranked[0]
        top2 = ranked[1]

        # Case 1: Same name and same type (e.g. multiple windows of same app frame) -> NOT ambiguous
        if top1.name.lower() == top2.name.lower() and top1.target_type == top2.target_type:
            return False, None

        # Case 2: Open tab displaying the exact same local service or same app window -> NOT ambiguous
        types = {top1.target_type, top2.target_type}
        if (
            types == {TargetType.EXISTING_BROWSER_TAB, TargetType.LOCAL_WEB_SERVICE}
            or types == {TargetType.EXISTING_WINDOW, TargetType.INSTALLED_DESKTOP_APP}
            or types == {TargetType.EXISTING_BROWSER_TAB, TargetType.PUBLIC_WEB_DOMAIN}
        ):
            if (
                top1.name.lower() in top2.name.lower()
                or top2.name.lower() in top1.name.lower()
                or top1.identity.rstrip("/") == top2.identity.rstrip("/")
            ):
                return False, None

        # Case 3: Same web origin (e.g. specific path vs root of same local/public host) -> NOT ambiguous, prefer top1
        if (
            top1.identity.startswith("http")
            and top2.identity.startswith("http")
            and (top1.identity.startswith(top2.identity.rstrip("/")) or top2.identity.startswith(top1.identity.rstrip("/")))
        ):
            return False, None

        # If both top candidates have high confidence and identical/very close scores
        if top1.score >= 0.80 and top2.score >= 0.80 and abs(top1.score - top2.score) < threshold_diff:
            # Different identities
            if top1.identity != top2.identity:
                reason = f"AMBIGUOUS_TARGET: Found multiple matching targets ('{top1.name}' [{top1.source}] vs '{top2.name}' [{top2.source}]). Please specify."
                return True, reason

        return False, None