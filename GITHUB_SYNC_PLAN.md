# PLUTON V2 — GITHUB REPOSITORY SYNCHRONIZATION PLAN

---

## 1. Prerequisites & Rules

1. **DO NOT PUSH AUTOMATICALLY**: All changes must be explicitly reviewed before pushing.
2. **Exclude Transient Artifacts**:
   - `data/screenshots/`
   - `data/test_pluton.db*`
   - `*.log` (e.g. `backend-server.log`, `frontend-server.log`)
   - `scratch/` (temporary debugging scripts)
   - `.pytest_cache/`, `__pycache__/`, `dist/`, `node_modules/`
3. **Commit Clean Production Tree**:
   - Commit `backend/` (including `core/contracts.py`, `router/`, `fast_plane/`).
   - Commit `frontend/` (full React/Vite application).
   - Commit `docs/` and root architectural specifications (`PLUTON_MASTER_ARCHITECTURE.md`, `MILESTONE_0_REPOSITORY_AUDIT.md`, etc.).

---

## 2. Updated `.gitignore` Specification

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
env/
venv/
*.sqlite3
data/*.db
data/*.db-wal
data/*.db-shm
data/screenshots/

# Logs & Diagnostics
*.log
@AutomationLog.txt
backend-server.log
frontend-server.log

# Node & Frontend
node_modules/
frontend/node_modules/
frontend/dist/
*.tsbuildinfo

# IDE & Testing
.pytest_cache/
.coverage
htmlcov/
.idea/
.vscode/
scratch/
```

---

## 3. Checkpoint Commit Plan

- **Branch**: `main`
- **Target Commit Message**: `feat(v2): Milestone 1 & Milestone 2 Canonical Architecture Reset (Core Contracts, Front-Door Router, Fast Plane)`
- **Verification Gate**: All 101 backend tests and 11 frontend tests must pass before git push.
