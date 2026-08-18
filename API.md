# API

The development API runs at `http://localhost:8000`; interactive documentation is at `/docs`.

Chat and approval endpoints support streaming (`{"stream": true}`) and respond with Server-Sent Events:

- `event: task` / `event: session` — identity created for this run
- `event: text` — progressive `{"delta": "..."}` chunks
- `event: activity` — tool/progress activity
- `event: confirmation` — HIGH-risk tool paused, awaiting approval
- `event: done` — final result
- `event: error` — terminal failure

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service health check |
| GET | `/api/settings/status` | Provider status (never exposes credentials) |
| GET | `/api/tools` | Registered tools and their permission levels |
| POST | `/api/chat` | Create and process a task (`{"message":"...","session_id":"?","stream":false}`) |
| GET | `/api/tasks` | Task history (optional `?session_id=` filter) |
| GET | `/api/tasks/{id}/confirmations` | Pending HIGH-risk actions for a task |
| POST | `/api/tasks/{id}/approve` | Approve pending actions and resume the agent |
| POST | `/api/tasks/{id}/deny` | Deny pending actions and resume the agent |
| GET / POST | `/api/sessions` | List or create conversations |
| DELETE | `/api/sessions/{id}` | Delete a conversation and its tasks |
| GET / POST | `/api/memories` | List or save an approved memory |
| DELETE | `/api/memories/{id}` | Delete a memory |

Task states: `RUNNING` → `CONFIRMING` (waiting for approval) → `COMPLETED` / `FAILED`.
