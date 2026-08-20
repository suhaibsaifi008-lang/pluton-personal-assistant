# PLUTON V2 — FRONTEND / BACKEND CONTRACT AUDIT

---

## 1. API Endpoints & Request / Response Schemas

| Endpoint | Method | Purpose | Request Schema | Response Schema / Stream |
| :--- | :---: | :--- | :--- | :--- |
| `/api/chat` | `POST` | Primary user interaction | `{ message: string, session_id?: string, stream?: boolean }` | SSE stream if `stream=true`; `ChatResponse` if `false`. |
| `/api/tasks/{id}/approve` | `POST` | Human-in-the-loop approval | `{ approved: true }` | Resumed SSE stream. |
| `/api/tasks/{id}/deny` | `POST` | High-risk action denial | `{ approved: false }` | Resumed SSE stream. |
| `/api/tasks/{id}/cancel` | `POST` | Immediate task cancellation | Empty payload | `204 No Content` / cancelled task state. |
| `/api/health` | `GET` | Runtime health verification | None | `{ status, version, runtime, timestamp, browser_detected }` |
| `/api/version` | `GET` | Runtime build identity | None | `{ name, version, build_id, phase, supported_tiers }` |

---

## 2. Server-Sent Events (SSE) Contract

| SSE Event Name | Payload Schema | Frontend Consumer Action |
| :--- | :--- | :--- |
| **`task`** | `{"task_id": string}` | Stores `activeTaskId`, sets task state to `PLANNING`. |
| **`text`** | `{"delta": string}` | Progressively streams assistant message text in real time. |
| **`activity`** | `{"name": string, "summary": string, "status"?: string, "diagnostics"?: object}` | Appends to activity history; renders diagnostic badge. |
| **`confirmation`**| `{"task_id": string, "confirmations": array}` | Halts UI, transitions state to `AWAITING_APPROVAL`, renders approval modal. |
| **`done`** | `{"task_id": string, "session_id": string, "message": string, "status": string}` | Finalizes assistant message, sets status to `COMPLETED`/`FAILED`. |
| **`error`** | `{"message": string}` | Sets status to `FAILED`, displays alert in message card. |

---

## 3. Fast Deterministic Result Rendering

- When `FastCapabilityExecutor` executes a date/time or calculation query:
  1. Emits `text` event with `{"delta": resp_msg}`.
  2. Emits `done` event with `{"task_id": ..., "status": "COMPLETED", "message": resp_msg}`.
  3. Emits 0 `activity` events.
- **Frontend Behavior**: Displays the clean assistant message immediately in the conversation thread without cluttering the UI with unneeded tool activities.
