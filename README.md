# PLUTON AI

PLUTON is a local-first personal AI-agent foundation. This first release provides a polished web interface, a FastAPI service, SQLite-backed task and memory records, an AI provider abstraction, and a permission-aware tool design.

It is intentionally not granted uncontrolled browser, terminal, or computer access. Those capabilities are added as individually permissioned tools — terminal access runs only after you approve it.

## What it does

- Persistent conversations (sessions) with streaming replies delivered progressively to the UI.
- A tool registry: read/write files in the approved workspace, safe terminal commands (approval-gated), web search and page fetch, and long-term memory recall/save.
- Task states: running → confirming (waiting for your approval) → completed / failed.
- Provider-neutral model interface (OpenAI today, other providers can be added without changing the agent).

## Architecture

```
React UI → FastAPI API → Agent engine → AI provider / tool registry
                         ↓
                    SQLite tasks + memory
```

The provider is replaceable: `backend/app/providers.py` defines `AIProvider`; OpenAI is one implementation and a safe local guide is used until a key is configured.

## Run on Windows

Install these two prerequisites first:

1. [Python 3.11+](https://www.python.org/downloads/) — tick **Add Python to PATH** during setup.
2. [Node.js LTS](https://nodejs.org/) — includes npm.

Then open PowerShell in this project folder and run:

```powershell
Copy-Item .env.example .env
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
```

Start the backend in one PowerShell window:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```

Start the interface in a second PowerShell window:

```powershell
Set-Location frontend
npm run dev
```

Open the address Vite prints (normally `http://localhost:5173`).

## AI configuration

To enable OpenAI chat, add `PLUTON_OPENAI_API_KEY=your_key_here` to `.env`. The key stays on the backend and is never sent to the browser. Without it, PLUTON still runs in a clear setup mode.

## Tests

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path + "\backend"
pytest backend\tests
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), [SECURITY.md](SECURITY.md), and [API.md](API.md).
