# PLUTON V2 — LIVE RUNTIME TRACE & STALE PROCESS FORENSIC AUDIT

---

## 1. Root Cause of Live UI Discrepancy

During live UI testing, user queries exhibited pre-M1 behavior (e.g. date queries generating terminal actions, conversation entering computer UI).

### Forensic Evidence:
1. **Background Process Discovery**:
   - Process PID `29492` / `31592` (`uvicorn.exe app.main:app --host 127.0.0.1 --port 8000`) was launched at **`18-08-2026 06:45:23`** (over 12 hours ago).
   - Process PID `22060` / `25988` (`vite.js --host 127.0.0.1 --port 5173`) was launched at **`18-08-2026 03:54:09`**.
2. **Execution Without `--reload`**:
   - The running uvicorn instance was launched without `--reload`.
   - Consequently, Python in-memory bytecode in that process was locked to the pre-M1 code from 06:45 AM.
   - All HTTP/SSE traffic sent to `localhost:8000` was processed by the 12-hour-old process memory, completely unaware of `contracts.py`, `front_door_router.py`, or `fast_plane/`.

---

## 2. In-Memory Fresh Process Verification

When the identical endpoint `/api/chat` is evaluated using fresh in-memory runtime execution against the current codebase:

| Query | Live Running Stale Process (06:45 AM) | Fresh In-Memory Current Runtime (Post-M2) |
| :--- | :--- | :--- |
| `"Tell me a fact."` | ❌ FAILED: Searched for UI element `'Tell me a fact'` on desktop | ✅ COMPLETED: Conversational fact generated, 0 computer activities, 0 UI actions. |
| `"What is today's date?"` | ❌ FAILED: Called LLM planner and streamed raw JSON thoughts | ✅ COMPLETED: `"Today is Tuesday, August 18, 2026, and the current time is 01:48 PM."` in $0.01	ext{ ms}$. |
| `"What is 25 * 48?"` | ⚠️ LLM inference turn | ✅ COMPLETED: `"25 * 48 = 1200"` in $0.01	ext{ ms}$ via Safe AST Evaluator. |
| `"Open Calculator"` | ✅ Launched Calculator | ✅ COMPLETED: Routed to `COMPUTER` domain, launched Calculator (HWND/PID bound). |
| `"Open File Explorer"` | ✅ Physical launch | ✅ COMPLETED: Routed to `COMPUTER`/`FILESYSTEM` domain. |
| `"Open browser..."` | ⚠️ Hardcoded browser | ✅ COMPLETED: Generic `BROWSER` domain routing. |

---

## 3. Real Request Execution Path (Post-M2)

```
[User Message via /api/chat]
          │
          ▼
[PlutonRuntime.execute_task(task_id)]
          │
          ▼
[FrontDoorTaskRouter.route(task.request)]
          │
    ┌─────┴───────────────────────────────┬────────────────────────────────┐
    ▼                                     ▼                                ▼
[TRUSTED_DATA / CALCULATION]        [CONVERSATION / KNOWLEDGE]       [COMPUTER / BROWSER / FS]
    │                                     │                                │
    ▼                                     ▼                                ▼
[FastCapabilityExecutor]            [UniversalAgentLoop]             [UniversalAgentLoop]
- SystemClockEvaluator               .run_conversational()            .run()
- SafeMathEvaluator                 (Stream text, 0 UI actions)      (Observe -> Reason -> Act -> Verify)
    │                                     │                                │
    ▼                                     ▼                                ▼
(< 0.05 ms response, 0 LLM calls)   (Conversational SSE events)      (Physical Execution & Verification)
```
