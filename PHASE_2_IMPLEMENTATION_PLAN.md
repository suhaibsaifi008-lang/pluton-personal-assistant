# PLUTON V2 — PHASE 2: AGENT INTELLIGENCE & CLOSED-LOOP PLANNING IMPLEMENTATION PLAN

**Document Version**: 2.1.0 (Formal Architecture Review Approved)  
**Phase**: Phase 2 — Agent Intelligence Layer  
**Core Thesis**: *The Computer Engine is the hands. Phase 2 builds the brain that maintains an explicit world model, plans governed capability workflows, verifies environmental consequences, and dynamically adapts based on reality.*

---

## 1. Architecture & Boundary Separation

The Phase 2 Agent Intelligence Layer is strictly separated from the frozen Universal Computer Subsystem (`backend/app/subsystems/computer/`).

```
                               ┌─────────────────────────────┐
                               │         USER REQUEST        │
                               └──────────────┬──────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────────┐
                               │    INTENT UNDERSTANDING     │
                               │  (Goal Extraction & Scope)  │
                               └──────────────┬──────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────────┐
                               │    DYNAMIC WORLD MODEL      │
                               │(Active Windows, Tabs, State)│
                               └──────────────┬──────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────────┐
                               │     TASK PLANNER & GRAPH    │
                               │ (Preconditions, Postconds)  │
                               └──────────────┬──────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────────┐
                               │   POLICY & RISK EVALUATOR   │
                               │(Risk Level, Approval Gates) │
                               └──────────────┬──────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────────┐
                               │    CLOSED-LOOP CONTROLLER   │
                               └──────────────┬──────────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    │                                                   │
                    ▼                                                   ▼
     ┌─────────────────────────────┐                     ┌─────────────────────────────┐
     │      ACT: COMPUTER ENGINE   │                     │      DIAGNOSE & RECOVER     │
     │  (Domain Handlers & Kernel) │                     │ (Target Refresh, Replanning)│
     └──────────────┬──────────────┘                     └──────────────▲──────────────┘
                    │                                                   │ (On Verification
                    ▼                                                   │  or Actuation
     ┌─────────────────────────────┐                                    │  Failure)
     │   OBSERVE & VERIFY STATE    │────────────────────────────────────┘
     │(Readback, State Deltas, UIA)│
     └──────────────┬──────────────┘
                    │ (On Success)
                    ▼
     ┌─────────────────────────────┐
     │    UPDATE WORLD MODEL &     │
     │     ADVANCE TASK STATE      │
     └─────────────────────────────┘
```

### Component Responsibility Boundary:

| Subsystem Layer | Components | Responsibility |
|---|---|---|
| **Phase 1 (Frozen Substrate)** | `ComputerEngine`, `TargetResolver`, 9 Domain Handlers, `BrowserEngine`, `UIA_ENGINE`, `ControlKernel`, `VerificationEngine`, Security Policies | Physical/OS actuation, target resolution, execution tiering, verification mechanics, security boundaries, hardware queue flushing. |
| **Phase 2 (Agent Intelligence)** | `IntentParser`, `WorldStateTracker`, `TaskPlanner`, `ClosedLoopExecutor`, `RecoveryEngine`, `MemoryManager`, `ObservabilityEmitter` | Intent decomposition, DAG planning, precondition/postcondition reasoning, closed-loop execution, failure diagnosis, replanning, user intervention. |

---

## 2. Structured World & Task State Model (`WorldState`)

The agent maintains an explicit, serializable, and observable world model split across 4 distinct state domains:

```python
@dataclass
class EnvironmentSnapshot:
    """Observable physical state of the desktop environment."""
    active_hwnd: int | None
    active_window_title: str
    active_process_name: str
    open_windows: list[dict[str, Any]]
    browser_state: dict[str, Any]       # Open tabs, active URL, title
    filesystem_context: dict[str, Any]  # Workspace root, modified files
    timestamp: float
    stale: bool = False

@dataclass
class TaskProgressModel:
    """Short-lived working state of the active task."""
    task_id: str
    goal: str
    subgoals: list[SubGoal]
    current_subgoal_index: int
    completed_actions: list[ActionRecord]
    failed_actions: list[ActionRecord]
    plan_revision: int = 1
    uncertainty_score: float = 0.0      # 0.0 (certain) to 1.0 (ambiguous)
    world_state: EnvironmentSnapshot
```

### State Invariants:
1. **Explicit, not inferred**: World state is sampled from deterministic OS sensors (`window.list`, `browser.get_state`, `UIA_ENGINE`), never hallucinated.
2. **Snapshotting**: Every action records `pre_state` and `post_state` snapshots to compute observable state deltas.
3. **Freshness Tracking**: Observations older than 5.0 seconds are flagged `stale=True` and refreshed before dependent actions execute.

---

## 3. Planner Model (`TaskPlanner`)

The planner decomposes high-level user intent into a Directed Acyclic Graph (DAG) of capability steps with explicit preconditions, postconditions, and risk levels:

```python
@dataclass
class PlanStep:
    step_id: str
    goal: str
    capability: CapabilityType           # Generic capability (e.g. BROWSER_NAVIGATE, KEYBOARD_TYPE)
    target: str                         # Target identity or semantic query
    parameters: dict[str, Any]          # Action parameters
    preconditions: list[Precondition]   # e.g. WindowMustBeOpen("Notepad"), TabMustExist("GitHub")
    postconditions: list[Postcondition] # e.g. WindowContainsText("Hello"), URLMatches("github.com")
    verification_strategy: VerificationStrategy
    risk_level: CommandRiskLevel
    fallback_strategy: str | None
    failure_handling: str = "diagnose_and_recover"
```

---

## 4. Capability Planning & Strategy Resolution

1. The planner reasons exclusively at the **capability level** (`app.launch`, `window.focus`, `keyboard.type`, `browser.navigate`, `ui.invoke`, etc.).
2. The planner **never** generates raw mouse coordinates, raw Win32 messages, or raw CDP commands.
3. The frozen Phase 1 Capability Router and Target Resolver map planned actions to the optimal execution tier (Tier 1 Native $\rightarrow$ Tier 2 Playwright $\rightarrow$ Tier 3 UIA $\rightarrow$ Tier 4 Verified Keyboard $\rightarrow$ Tier 5 Vision $\rightarrow$ Tier 6 Coordinate Mouse).

---

## 5. Closed-Loop Execution Engine (`ClosedLoopExecutor`)

Every step in the execution graph strictly executes through the verified closed loop:

$$\text{PLAN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE} \longrightarrow \text{VERIFY} \longrightarrow \text{UPDATE STATE} \longrightarrow \text{REPLAN (if needed)}$$

```python
async def execute_step(step: PlanStep, context: ExecutionContext) -> StepResult:
    # 1. Check Preconditions
    pre_ok, pre_err = await check_preconditions(step.preconditions, context)
    if not pre_ok:
        return await RECOVERY_ENGINE.handle_precondition_failure(step, pre_err, context)

    # 2. Capture Pre-Action Snapshot
    pre_snapshot = await WORLD_STATE_TRACKER.capture_snapshot()

    # 3. ACT: Execute via Computer Engine
    tool_res = await COMPUTER_ENGINE.execute_action(
        Action(
            id=step.step_id,
            capability=step.capability,
            target=step.target,
            parameters=step.parameters,
            tier_requested=ExecutionTier.TIER_1_NATIVE_API,
        ),
        context=context,
    )

    # 4. OBSERVE: Capture Post-Action Snapshot
    post_snapshot = await WORLD_STATE_TRACKER.capture_snapshot()

    # 5. VERIFY: Verify environmental postconditions and tool result
    ver_res = VERIFICATION_ENGINE.verify_action(
        strategy=step.verification_strategy,
        expected_state=step.postconditions[0].expected_value if step.postconditions else None,
        target=step.target,
        metadata=step.parameters,
    )

    # 6. UPDATE OR RECOVER
    if tool_res.status == "completed" and ver_res.verified:
        await WORLD_STATE_TRACKER.update(step, pre_snapshot, post_snapshot, tool_res, ver_res)
        return StepResult.SUCCESS
    else:
        return await RECOVERY_ENGINE.diagnose_and_recover(step, pre_snapshot, post_snapshot, tool_res, ver_res, context)
```

---

## 6. Verification Feedback Loop & State Deltas

* **No Blind Trust**: An action is never assumed successful because the subprocess returned 0 or the keyboard driver emitted scan codes. Success strictly requires `ver_res.verified == True` and matching state deltas.
* **State Delta Detection**: If an action was expected to change the active window or open a tab, but `post_snapshot == pre_snapshot`, a silent actuation failure is flagged and routed to diagnosis.

---

## 7. Structured Recovery Engine (`RecoveryEngine`)

The recovery engine replaces generic retries with 5 distinct recovery pathways:

```
                                  ┌───────────────────────────┐
                                  │      FAILURE OCCURRED     │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │    DIAGNOSE ROOT CAUSE    │
                                  └─────────────┬─────────────┘
                                                │
         ┌───────────────┬──────────────────────┼──────────────────────┬───────────────┐
         ▼               ▼                      ▼                      ▼               ▼
   ┌───────────┐  ┌─────────────┐       ┌───────────────┐        ┌───────────┐  ┌──────────────┐
   │ 1. RETRY  │  │2. RE-RESOLVE│       │  3. STRATEGY  │        │ 4. REPLAN │  │   5. USER    │
   │(Transient)│  │ (Stale HWND/│       │   FALLBACK    │        │ (DAG/Goal │  │ INTERVENTION │
   │           │  │  Focus Loss)│       │ (UIA -> Keyb) │        │ Mutation) │  │  (Ambiguity) │
   └───────────┘  └─────────────┘       └───────────────┘        └───────────┘  └──────────────┘
```

| Recovery Pathway | Trigger Condition | Execution Mechanism |
|---|---|---|
| **1. RETRY** | Transient timing jitter, UI animation delay ($< 500\text{ms}$). | Re-execute same action after short settle delay (max 2 attempts). |
| **2. RE-RESOLVE** | Target window lost focus, minimized, or HWND became stale. | Re-acquire window focus, bring to foreground, re-resolve HWND via `TargetResolver`. |
| **3. STRATEGY FALLBACK** | Primary execution tier failed (e.g. UIA ValuePattern not supported on custom edit control). | Escalate to alternative execution tier (e.g. Tier 4 Verified Keyboard Entry). |
| **4. REPLAN** | Environmental prerequisite changed (e.g. Tab was closed externally, directory moved). | Mutate plan DAG to add prerequisite subgoals and resume execution. |
| **5. USER INTERVENTION** | Unresolvable ambiguity (`AMBIGUOUS_TARGET`), critical safety block, or exhausted retries. | Stream interactive choice prompt to frontend `/api/chat` and pause execution. |

---

## 8. Failure Taxonomy

Pluton V2 classifies all failures into 11 explicit categories:

1. `TARGET_NOT_FOUND`: Target window, tab, or element does not exist.
2. `AMBIGUOUS_TARGET`: Multiple candidates match query with equal confidence.
3. `POLICY_DENIED`: Operation blocked by security policy (terminal command risk or filesystem boundary).
4. `AUTHORIZATION_FAILED`: Kernel token invalid, expired, or revoked.
5. `PRECONDITION_FAILED`: Environmental prerequisite not satisfied before action.
6. `EXECUTION_FAILED`: OS/driver actuation error.
7. `VERIFICATION_FAILED`: Expected state change was not observed post-action.
8. `ENVIRONMENT_CHANGED`: Target disappeared or active context switched during action.
9. `TIMEOUT`: Operation or verification exceeded maximum duration.
10. `RECOVERY_EXHAUSTED`: Maximum recovery attempts reached without success.
11. `USER_INTERVENTION_REQUIRED`: Execution suspended pending human input/approval.

---

## 9. Policy & Risk Pre-Evaluation

* **Upfront Gate**: Security policy evaluation (`TerminalSecurityPolicy`, `FilesystemSecurityPolicy`) happens **before** execution.
* **Risk Pruning**: `CRITICAL` commands are rejected at plan time.
* **Approval Flow**: `HIGH` risk actions generate a `PauseForConfirmation` event with full contextual justification and stream it to the user.

---

## 10. Memory Architecture (Working vs Persistent)

| Memory Layer | Storage | Lifecycle | Content |
|---|---|---|---|
| **Working Task State** | In-Memory (`TaskProgressModel`) | Per-Task Duration | Active plan DAG, step history, pre/post snapshots, current recovery state. |
| **Persistent Session Memory** | SQLite (`backend/app/db/database.py`) | Cross-Session | Completed task summaries, verified app paths, user preferences, activity logs. |

---

## 11. Concurrency & Task Isolation

* **Isolated Task Instances**: Every task receives its own `TaskProgressModel` and `ExecutionContext` bound to `task_id`.
* **Zero Shared Mutable State**: Global state is strictly prohibited in the planner and executor.
* **Single Active Computer Controller**: `ComputerControlKernel` enforces that only one task can actuate physical hardware at any given instant.

---

## 12. Observability & Event Stream Schema

Real-time structured events emitted over SSE `/api/chat`:
* `plan_generated`: Full DAG with steps, goals, and risk levels.
* `step_started`: Step ID, capability, target, parameters.
* `step_observed`: Pre/post state deltas.
* `step_verified`: Verification strategy, verified status, latency.
* `recovery_triggered`: Failure category, diagnostic reason, recovery pathway chosen.
* `world_updated`: Updated environment snapshot.

---

## 13. Testing Strategy

1. **Unit Tests (`test_v2_planner.py`)**: Goal decomposition, DAG ordering, precondition logic, risk classification.
2. **Integration Tests (`test_v2_closed_loop.py`)**: End-to-end closed-loop executor with simulated state transitions.
3. **Adversarial Recovery Tests (`test_v2_recovery_engine.py`)**: Injected mid-task window closures, focus loss, and verification timeouts.
4. **Real Desktop Closed-Loop Acceptance**: Live end-to-end user workflows tested on Windows.

---

## 14. Performance Safeguards
* **Cached Window Handle Queries**: Window enumeration uses Win32 cache ($< 2\text{ms}$).
* **Lazy Vision & Capture**: Screenshots and vision grounding are invoked only when structured UIA/DOM handles are unavailable.
* **Reused Browser Contexts**: Sequential browser actions within a task reuse the active Playwright context.

---

## 15. Explicit Non-Goals
* **No modification of the frozen Computer Subsystem**.
* **No bypass of user confirmation for high-risk actions**.
* **No open-loop unverified execution**.
* **No secondary computer-control APIs**.
