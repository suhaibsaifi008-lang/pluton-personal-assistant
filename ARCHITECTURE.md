# Architecture

PLUTON separates reasoning from capability. The agent engine chooses a provider and orchestrates tools; providers never own file, browser, or computer access.

- `frontend/`: Vite + React interface.
- `backend/app/main.py`: HTTP API and application lifecycle (SSE streaming, sessions, approvals).
- `backend/app/agent.py`: bounded planner/executor loop with tool-calling, streaming, and confirmation hand-offs.
- `backend/app/providers.py`: provider abstraction; add Claude/Gemini/local implementations here.
- `backend/app/tools.py`: typed, permission-gated tool registry (filesystem, terminal, web, memory).
- `backend/app/security.py`: central risk classification.
- `backend/app/models.py`: SQLite session, task, and memory persistence.

## Flow

```
React UI ──SSE──▶ FastAPI API ──▶ AgentEngine loop ──▶ AI provider / tool registry
                                          │
                                          ▼
                                SQLite sessions + tasks + memory
```

- **Task states**: `RUNNING` → `CONFIRMING` (paused for a HIGH-risk tool) → `COMPLETED` / `FAILED`. A paused task stores a checkpoint; `approve`/`deny` resumes the loop.
- **Providers are neutral**: `AIProvider.respond` and `stream_respond` define the contract. `ProviderRequest` carries `context` (recalled memories) and `history` (session turns) so every provider can be wired identically.
- **Tools carry permission levels**: `low`/`medium` run automatically; `high` (terminal) always waits for explicit user approval and refuses destructive command patterns.

Tool execution, streaming responses, sessions, and memory recall are implemented. The next milestone is time-based scheduling and the Automations view.