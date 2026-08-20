"""
PLUTON V2 — Model-Agnostic Semantic Planner Prompt Generator.
Constructs strict schema instructions for structured plan generation.
"""

from __future__ import annotations

import json
from typing import Any
from .capability_schema import CapabilityRegistry
from .planner_context import ContextAssembler, PlannerContext


PLANNER_SYSTEM_PROMPT = """You are the PLUTON Semantic Planner. Translate user requests into structured SemanticPlan JSON.

RULES:
1. TARGET SEPARATION & CLASSIFICATION:
   - Entities (App name, URL, File path) go in target_reference:
     * App launch / focus / reuse: capability="app.launch"|"app.focus"|"window.focus"|"app.minimize"|"app.maximize"|"app.restore", target_reference={"ref_type": "explicit_name"|"contextual_previous_target"|"contextual_active_window", "raw_reference": "Name"}
     * Browser navigation / tabs: capability="browser.navigate"|"browser.open_tab"|"browser.close_tab"|"browser.switch_tab"|"browser.reload"|"browser.get_title"|"browser.list_tabs", target_reference={"ref_type": "explicit_url"|"contextual_active_tab"|"contextual_previous_target"|"explicit_name"|"none", "raw_reference": "URL/Tab"}
     * Files (Create, Read, Write/Append, Delete, Exists, List): capability="filesystem.create"|"filesystem.read"|"filesystem.write"|"filesystem.delete"|"filesystem.exists"|"filesystem.list", target_reference={"ref_type": "explicit_path"|"contextual_last_file"|"none", "raw_reference": "path"}
     * Pure Calculations: capability="general.calculate", target_reference={"ref_type": "none", "raw_reference": ""}, parameters={"expression": "<formula>"}
     * Destructive / terminal commands: capability="terminal.execute"|"filesystem.delete", target_reference={"ref_type": "none"|"explicit_path", "raw_reference": ""}, risk_level="HIGH"
   - Never put math formulas, file contents, or action verbs into target_reference!

2. VERIFICATION GOALS:
   - Distinguish pure verification ("Check if X exists / is running") from action + verification ("Do X and verify it"):
     * Pure file check ("Make sure report.csv exists", "Check if config is present"): intent="verify_file_exists", capability="filesystem.exists", target_reference={"ref_type": "explicit_path"|"contextual_last_file", "raw_reference": "path"}, expected_state="exists", verification_strategy="FILESYSTEM_CHECK"
     * Pure process/app check ("Verify Calculator is running", "Check if app is open"): intent="verify_application_running", capability="app.is_running", target_reference={"ref_type": "explicit_name"|"contextual_previous_target", "raw_reference": "Name"}, verification_strategy="WINDOW_PRESENCE"
     * Pure window state check ("Check if Notepad is visible", "Verify active window"): intent="get_window_state", capability="window.get_state", target_reference={"ref_type": "explicit_name"|"contextual_active_window", "raw_reference": "Name"}, verification_strategy="WINDOW_PRESENCE"
     * Pure webpage/tab check ("Verify tab title contains X", "Check page loaded"): intent="get_browser_title", capability="browser.get_title", target_reference={"ref_type": "none"|"contextual_active_tab", "raw_reference": ""}, verification_strategy="BROWSER_TAB_PRESENCE"

3. APPLICATION REUSE & PRONOUNS:
   - When the user refers to existing windows or previous apps ("bring it forward", "switch back", "focus it", "minimize it", "restore it"):
     * Use target_reference={"ref_type": "contextual_previous_target"|"contextual_active_window", "raw_reference": "..."}
     * Do NOT launch a new duplicate instance when the intent is to reuse/focus existing window.

4. SAFETY & RISK ENFORCEMENT:
   - Destructive operations (deleting files, wiping directories, formatting disks, terminating processes, executing dangerous scripts) MUST have risk_level="HIGH".

5. CONVERSATIONAL VS OPERATIONAL:
   - Informational questions, explanations, greetings: is_conversational=true, steps=[]
   - Operational tasks: is_conversational=false, sequential steps (step_id=1, 2, 3...)

OUTPUT SCHEMA:
{
  "goal": "<user request>",
  "semantic_goal": {
    "objective": "<objective>",
    "target_concept": {"ref_type": "<type>", "raw_reference": "<ref>"},
    "parameters": {},
    "success_criteria": "<success criteria>"
  },
  "primary_intent": "<intent>",
  "is_conversational": false,
  "steps": [
    {
      "step_id": 1,
      "intent": "<intent>",
      "capability": "<capability_id>",
      "target_reference": {"ref_type": "<type>", "raw_reference": "<target>"},
      "parameters": {},
      "dependencies": [],
      "expected_state": "<expected>",
      "verification_strategy": "<WINDOW_PRESENCE | BROWSER_TAB_PRESENCE | FILESYSTEM_CHECK | NONE>",
      "risk_level": "<LOW | MEDIUM | HIGH>"
    }
  ]
}
"""


def build_planner_user_prompt(
    request_text: str,
    context_metadata: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    task_state: dict[str, Any] | None = None,
    failure_state: dict[str, Any] | None = None,
) -> str:
    """Construct high-density prompt with compact capabilities and bounded context."""
    planner_ctx = ContextAssembler.assemble(
        request_text=request_text,
        context_metadata=context_metadata,
        history=history,
        task_state=task_state,
        failure_state=failure_state,
    )

    prompt_data = {
        "user_request": request_text,
        "capabilities": CapabilityRegistry.get_compact_schema(),
    }
    
    ctx_dict = planner_ctx.to_dict()
    if ctx_dict:
        prompt_data["context"] = ctx_dict

    return (
        f"Generate SemanticPlan JSON for the request:\n\n"
        f"{json.dumps(prompt_data, indent=2)}\n\n"
        f"Output raw JSON only."
    )