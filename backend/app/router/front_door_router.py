"""PLUTON V2 — Front-Door Task Router.

Determines the authoritative target execution domain for user requests:
- CONVERSATION / KNOWLEDGE -> direct conversational streaming (zero computer execution)
- TRUSTED_DATA / CALCULATION -> instant deterministic capability (< 5ms, zero model call)
- COMPUTER / BROWSER / FILESYSTEM / TERMINAL -> existing computer execution pipeline
- MULTI_DOMAIN -> compound agent workflow
- AMBIGUOUS -> safety clarification fallback

Strictly side-effect free and provider-independent.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional
from app.core.contracts import ContractValidationError, IntentDomain, Task
from .contracts import RouteContext, RouteDecision


class FrontDoorTaskRouter:
    """Front-Door Task Router deciding domain routing before computer execution."""

    def route(self, task: Task | str, context: Optional[RouteContext] = None) -> RouteDecision:
        """Routes a Task or request string to its authoritative target domain."""
        t0 = time.perf_counter()

        if isinstance(task, str):
            req_text = task.strip()
            task_id = ""
        elif isinstance(task, Task):
            req_text = task.user_request.strip()
            task_id = task.task_id
        else:
            raise ContractValidationError(f"Invalid task input to router: {type(task)}")

        if not req_text:
            return RouteDecision(
                domain=IntentDomain.CONVERSATION,
                confidence=1.0,
                reason="empty_request",
                is_ambiguous=True,
                task_id=task_id,
            )

        norm_req = req_text.lower()

        # ---------------------------------------------------------------------
        # 1. Multi-Domain Compound Intent Detection
        # ---------------------------------------------------------------------
        has_compound_conjunction = any(conj in norm_req for conj in (" and then ", " and calculate ", " and type ", " and compute ", " and open ", " then calculate "))
        has_app_action = bool(re.search(r"\b(?:open|launch|start|run|bring\s+up)\b", norm_req))
        has_math_action = any(m in norm_req for m in ("calculate", "compute", "solve", "+", "*", "-", "/"))

        if has_compound_conjunction and has_app_action and has_math_action:
            return RouteDecision(
                domain=IntentDomain.MULTI_DOMAIN,
                confidence=0.95,
                reason="compound_app_and_calculation",
                requires_computer_agent=True,
                requires_model=True,
                task_id=task_id,
            )

        # ---------------------------------------------------------------------
        # 2. Deterministic Fast Capabilities (Stage 1)
        # ---------------------------------------------------------------------
        # A. Trusted Date / Time Query
        date_time_patterns = [
            r"^(?:what\s+is\s+|what\'?s\s+|tell\s+me\s+)?(?:the\s+)?(?:current\s+)?(?:date|time|day|year|month)(?:\s+today|\s+now)?\??$",
            r"^(?:what\s+is\s+|what\'?s\s+|tell\s+me\s+)?today\'?s\s+date\??$",
            r"^(?:what\s+time\s+is\s+it)(?:\s+now|\s+today)?\??$",
            r"^(?:current\s+time|current\s+date)\??$",
        ]
        is_date_time = any(re.search(pat, norm_req) for pat in date_time_patterns)
        if is_date_time and not has_app_action:
            tz_match = re.search(r"\b(?:in|for)\s+([a-zA-Z_\/]+)$", norm_req)
            tz_val = tz_match.group(1) if tz_match else None
            return RouteDecision(
                domain=IntentDomain.TRUSTED_DATA,
                confidence=1.0,
                capability_id="system.time",
                reason="deterministic_system_time",
                requires_current_data=True,
                requires_computer_agent=False,
                requires_model=False,
                parameters={"timezone": tz_val},
                task_id=task_id,
            )

        # B. Pure Arithmetic / Calculation Query
        is_calc_query = bool(re.search(r"^(?:what\s+is\s+|what\'?s\s+|calculate\s+|compute\s+|solve\s+|evaluate\s+)?([\d\s\+\-\*\/\(\)\.\%\^xX]+)\??$", req_text.strip()))
        has_operator = any(op in req_text for op in ("+", "-", "*", "/", "%", "^", "times", "divided", "plus", "minus"))
        has_digits = bool(re.search(r"\d", req_text))

        if (is_calc_query or (has_operator and has_digits)) and not has_app_action:
            clean_expr = re.sub(r"^(?:what\s+is\s+|what\'?s\s+|calculate\s+|compute\s+|solve\s+|evaluate\s+)", "", req_text.strip(), flags=re.IGNORECASE).rstrip("?").strip()
            if clean_expr and re.search(r"\d", clean_expr) and not any(w in norm_req for w in ("open", "launch", "file", "tab", "window")):
                return RouteDecision(
                    domain=IntentDomain.CALCULATION,
                    confidence=1.0,
                    capability_id="general.calculate",
                    reason="deterministic_safe_math",
                    requires_computer_agent=False,
                    requires_model=False,
                    parameters={"expression": clean_expr},
                    task_id=task_id,
                )

        # ---------------------------------------------------------------------
        # 3. Conversational / Informational Inquiries (Pre-filter)
        # ---------------------------------------------------------------------
        # Requests starting with question/exploratory phrases are conversational UNLESS they contain
        # an explicit imperative command directed at the system (e.g. "can you open calculator").
        is_question_or_chat = any(norm_req.startswith(p) for p in (
            "explain ", "what is ", "what are ", "what was ", "what were ", "how does ", "how do ",
            "why does ", "why do ", "why is ", "why are ", "tell me about ", "tell me a ",
            "define ", "describe ", "summarize ", "summarize the concept of ",
            "how are you", "who is ", "who are ", "who was ", "where is ", "where are ",
            "compare ", "difference between ", "differences between ", "which is better ",
            "can you explain ", "could you explain ", "can you tell me ", "could you tell me ",
            "help me understand ", "i want to know about ", "hello", "hi ", "hey", "good morning",
            "good afternoon", "good evening", "thank you", "thanks",
        ))

        # Imperative creative writing requests (e.g. "write a poem", "write an essay", "compose a story")
        # are conversational unless they specify a file destination (e.g. "write ... to file.txt").
        is_creative_writing = bool(re.search(r"^(?:write|compose|draft|generate|create)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:poem|story|essay|email|summary|haiku|joke|letter|paragraph|code|script|function|class|song|dialogue|post)\b", norm_req))
        has_file_destination = any(k in norm_req for k in ("to file", "in file", "to disk", "into file", ".txt", ".py", ".md", ".json", ".csv"))

        if is_creative_writing and not has_file_destination:
            return RouteDecision(
                domain=IntentDomain.CONVERSATION,
                confidence=0.98,
                reason="creative_writing_conversational",
                requires_computer_agent=False,
                requires_model=True,
                task_id=task_id,
            )

        # Explicit imperative computer action verbs targeting desktop entities
        has_imperative_app_cmd = bool(re.search(r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:open|launch|start|run|bring\s+up|close|quit|exit|kill|terminate|switch\s+to|focus|minimize|maximize|restore)\s+(?:the\s+|my\s+)?([a-zA-Z0-9_\.\-]+)", norm_req))
        has_imperative_browser_cmd = bool(re.search(r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:navigate\s+to|go\s+to|search\s+(?:for|on|in)|search\s+google|search\s+youtube|google\s+search)\b", norm_req))
        has_imperative_fs_cmd = bool(re.search(r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:create|make|delete|remove|read|write\s+to|save\s+to)\s+(?:a\s+|the\s+)?(?:file|folder|directory)\b", norm_req)) or has_file_destination
        has_imperative_terminal_cmd = bool(re.search(r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:execute|run)\s+(?:the\s+)?(?:command|terminal|powershell|cmd|bash|script)\b", norm_req))
        has_imperative_ui_click = bool(re.search(r"^(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:click|double\s+click|right\s+click|press|type\s+into|drag|scroll)\s+(?:on|the|button|icon|box|input|link|menu)\b", norm_req))

        is_explicit_computer_cmd = (
            has_imperative_app_cmd
            or has_imperative_browser_cmd
            or has_imperative_fs_cmd
            or has_imperative_terminal_cmd
            or has_imperative_ui_click
        )

        if is_question_or_chat and not is_explicit_computer_cmd:
            return RouteDecision(
                domain=IntentDomain.CONVERSATION,
                confidence=0.98,
                reason="conversational_inquiry",
                requires_computer_agent=False,
                requires_model=True,
                task_id=task_id,
            )

        # ---------------------------------------------------------------------
        # 4. Computer / Desktop Automation Actions
        # ---------------------------------------------------------------------
        if is_explicit_computer_cmd:
            if has_imperative_fs_cmd or any(w in norm_req for w in ("create file", "delete file", "save to file", "folder", "directory")):
                domain = IntentDomain.FILESYSTEM
            elif has_imperative_terminal_cmd or any(w in norm_req for w in ("powershell", "terminal", "execute command")):
                domain = IntentDomain.TERMINAL
            elif has_imperative_browser_cmd or any(w in norm_req for w in ("navigate to", "search for", "search on", "search in", "google", "youtube", "browser tab")):
                domain = IntentDomain.BROWSER
            else:
                domain = IntentDomain.COMPUTER

            return RouteDecision(
                domain=domain,
                confidence=0.95,
                reason=f"computer_automation_{domain.value}",
                requires_computer_agent=True,
                requires_model=True,
                task_id=task_id,
            )

        # ---------------------------------------------------------------------
        # 5. Default General-Purpose Action Lane (Lane 2 ReAct Loop)
        # ---------------------------------------------------------------------
        return RouteDecision(
            domain=IntentDomain.COMPUTER,
            confidence=0.85,
            reason="general_purpose_agent_lane",
            requires_computer_agent=True,
            requires_model=True,
            task_id=task_id,
        )


FRONT_DOOR_ROUTER = FrontDoorTaskRouter()
