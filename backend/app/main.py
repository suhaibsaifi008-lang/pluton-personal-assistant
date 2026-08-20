import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent import AgentEngine
from .config import get_settings
from .database import Base, engine, get_db, migrate, reconcile_stale_tasks
from .memory_service import memory_service
from .models import Activity, Memory, Session as SessionModel, Task
from .schemas import ActivityOut, ChatRequest, ChatResponse, DecisionRequest, MemoryCreate, MemoryOut, SessionCreate, SessionOut, TaskOut, ToolActivity, ToolOut
from .tools import tool_metadata



@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate()
    reconcile_stale_tasks()
    from app.subsystems.computer.conformance import CONFORMANCE_VERIFIER
    CONFORMANCE_VERIFIER.audit_all()
    yield


app = FastAPI(title="PLUTON AI", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
import sys

_BACKEND_START_TIME = datetime.now(timezone.utc).isoformat()
RUNTIME_BUILD_ID = "pluton-v2-m2.1-recertified-20260818"

@app.get("/api/health")
def health_check():
    """Authoritative backend health and runtime verification endpoint."""
    from .tools.native_browser_controller import NATIVE_BROWSER
    brave_win = NATIVE_BROWSER.find_browser_window("Brave")
    return {
        "status": "ok",
        "name": "PLUTON AI",
        "version": "0.2.1",
        "build_id": RUNTIME_BUILD_ID,
        "runtime": "v2_canonical",
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "port": 8000,
        "start_time": _BACKEND_START_TIME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "browser_detected": brave_win is not None,
        "browser_hwnd": brave_win["hwnd"] if brave_win else None,
    }

@app.get("/api/version")
def version_check():
    """Expose runtime build identifier and capability surface with live process identity."""
    return {
        "name": "PLUTON AI",
        "version": "0.2.1",
        "build_id": RUNTIME_BUILD_ID,
        "phase": "M2.1: Execution Truth & Browser Interaction",
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "port": 8000,
        "start_time": _BACKEND_START_TIME,
        "python_version": sys.version,
        "supported_tiers": [1, 2, 3, 4, 5, 6],
    }

@app.get("/api/debug/runtime/engine-registry")
@app.get("/api/debug/runtime/conformance")
def runtime_engine_registry():
    """Live developer diagnostics showing engine classes, modules, capabilities, and interface conformance."""
    from app.subsystems.computer.conformance import CONFORMANCE_VERIFIER
@app.get("/api/debug/runtime/active-tasks")
def runtime_active_tasks():
    """List all currently active tasks in the Pluton runtime."""
    from .kernel.task_registry import ACTIVE_TASK_REGISTRY
    return {
        "active_task_count": ACTIVE_TASK_REGISTRY.count(),
        "active_tasks": ACTIVE_TASK_REGISTRY.list_active_tasks(),
    }

@app.get("/api/debug/runtime/input-audit")
def runtime_input_audit():
    """Diagnostic audit log of all low-level physical computer input attempts."""
    from .kernel.input_interceptor import PHYSICAL_INPUT_INTERCEPTOR
    return {
        "records": PHYSICAL_INPUT_INTERCEPTOR.get_audit_log(),
    }

@app.post("/api/control/emergency-stop")
def emergency_stop_endpoint():
    """Universal emergency kill switch: revokes all tokens, cancels all tasks, and flushes inputs."""
    from .kernel.control_kernel import KERNEL
    return KERNEL.emergency_stop()


def sse_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _drain_engine(task_id: str) -> None:
    """Consume the engine async generator to completion for background tasks."""
    try:
        async for _ in AgentEngine().run(task_id):
            pass
    except Exception:
        pass


def _stream_response(task_id: str) -> StreamingResponse:

    async def generate():
        last_event_was_terminal = False
        try:
            yield sse_frame("task", {"task_id": task_id})
            async for event, data in AgentEngine().run(task_id):
                yield sse_frame(event, data)
                if event in ("done", "error"):
                    last_event_was_terminal = True
        except asyncio.CancelledError:
            # Client disconnected — immediately revoke kernel token, mark task cancelled, and flush inputs
            try:
                from .kernel.control_kernel import KERNEL
                from .kernel.task_registry import ACTIVE_TASK_REGISTRY
                KERNEL.revoke_task(task_id)
                ACTIVE_TASK_REGISTRY.mark_cancelled(task_id, reason="client_disconnected")
                ACTIVE_TASK_REGISTRY.unregister_task(task_id, reason="client_disconnected")

                from .database import SessionLocal
                from .models import Task, TaskStatus
                with SessionLocal() as _db:
                    _task = _db.get(Task, task_id)
                    if _task and _task.status in ("RUNNING", "CONFIRMING", "EXECUTING"):
                        _task.status = TaskStatus.CANCELLED.value
                        _task.response = "Task cancelled due to client disconnect."
                        _db.commit()
            except Exception:
                pass
            raise
        except Exception as error:
            if not last_event_was_terminal:
                yield sse_frame("error", {"message": str(error)})
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



def _stream_resume(task_id: str, approved: bool) -> StreamingResponse:
    async def generate():
        last_event_was_terminal = False
        try:
            async for event, data in AgentEngine().resume(task_id, approved):
                yield sse_frame(event, data)
                if event in ("done", "error"):
                    last_event_was_terminal = True
        except asyncio.CancelledError:
            try:
                from .kernel.control_kernel import KERNEL
                from .kernel.task_registry import ACTIVE_TASK_REGISTRY
                KERNEL.revoke_task(task_id)
                ACTIVE_TASK_REGISTRY.mark_cancelled(task_id, reason="client_disconnected")
                ACTIVE_TASK_REGISTRY.unregister_task(task_id, reason="client_disconnected")
            except Exception:
                pass
            raise
        except Exception as error:
            if not last_event_was_terminal:
                yield sse_frame("error", {"message": str(error)})
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



@app.get("/api/health")
def health():
    return {"status": "ok", "name": "PLUTON AI"}


@app.get("/api/debug/runtime")
def debug_runtime():
    """Live runtime diagnostics endpoint for validating live process module identity."""
    import inspect
    import os
    import sys
    from app.core.runtime import PlutonRuntime
    from app.subsystems.computer.browser_engine import BROWSER_ENGINE
    from app.tools.uia_engine import UIA_ENGINE

    uia_source = ""
    if hasattr(UIA_ENGINE, "find_elements_by_query"):
        try:
            uia_source = inspect.getsource(UIA_ENGINE.find_elements_by_query)
        except Exception:
            uia_source = "Source extraction failed"

    return {
        "build_id": "PLUTON-V2-PHASE1-CERTIFIED-2026.08.17",
        "pid": os.getpid(),
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
        "app_module_path": inspect.getfile(debug_runtime),
        "uia_engine_module_path": inspect.getfile(UIA_ENGINE.__class__),
        "uia_engine_class": UIA_ENGINE.__class__.__name__,
        "has_find_elements_by_query": hasattr(UIA_ENGINE, "find_elements_by_query"),
        "find_elements_by_query_source_snippet": uia_source[:200] if uia_source else "",
        "browser_engine_module_path": inspect.getfile(BROWSER_ENGINE.__class__),
        "browser_engine_class": BROWSER_ENGINE.__class__.__name__,
        "runtime_module_path": inspect.getfile(PlutonRuntime),
    }


@app.get("/api/settings/status")
def provider_status():
    settings = get_settings()
    is_freellmapi = settings.ai_provider.lower() == "freellmapi"
    configured = bool(settings.freeLLMAPI_api_key) if is_freellmapi else bool(settings.openai_api_key)
    model = settings.freeLLMAPI_model if is_freellmapi else settings.openai_model
    supports_vision = configured
    return {
        "provider": settings.ai_provider,
        "model": model,
        "configured": configured,
        "supports_vision": supports_vision,
    }


@app.get("/api/tools", response_model=list[ToolOut])
def list_tools():
    return tool_metadata()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    session = None
    if payload.session_id:
        session = db.get(SessionModel, payload.session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        session.updated_at = datetime.now(timezone.utc)
    else:
        session = SessionModel(title=payload.message[:80])
        db.add(session)
        db.flush()
    task = Task(session_id=session.id, title=payload.message[:80], request=payload.message, status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    db.refresh(session)
    if payload.stream:
        return _stream_response(task.id)

    engine = AgentEngine()
    response = ChatResponse(task_id=task.id, session_id=session.id, message="", status=task.status, activities=[], confirmations=[])
    async for event, data in engine.run(task.id):
        if event == "activity":
            response.activities.append(ToolActivity(**data))
        elif event == "confirmation":
            response.confirmations = data["confirmations"]
            response.status = "CONFIRMING"
        elif event == "done":
            response.message, response.status = data["message"], data["status"]
        elif event == "error":
            response.message, response.status = data["message"], "FAILED"
    return response


@app.post("/api/tasks/{task_id}/approve")
async def approve_task(task_id: str, payload: DecisionRequest | None = None, db: Session = Depends(get_db)):
    return await _decision(task_id, True, payload, db)


@app.post("/api/tasks/{task_id}/deny")
async def deny_task(task_id: str, payload: DecisionRequest | None = None, db: Session = Depends(get_db)):
    return await _decision(task_id, False, payload, db)


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    from .kernel.control_kernel import KERNEL
    from .kernel.task_registry import ACTIVE_TASK_REGISTRY
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    KERNEL.revoke_task(task_id)
    ACTIVE_TASK_REGISTRY.mark_cancelled(task_id, reason="User cancelled task")
    task.status = "CANCELLED"
    db.commit()
    return {"task_id": task_id, "status": "CANCELLED"}



async def _decision(task_id: str, approved: bool, payload: DecisionRequest | None, db: Session):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    
    if task.status != "CONFIRMING":
        raise HTTPException(409, f"Task is not waiting for approval (current status: '{task.status}')")

    if payload and payload.stream:
        return _stream_resume(task.id, approved)


    engine = AgentEngine()
    result = ChatResponse(task_id=task.id, session_id=task.session_id, message="", status="RUNNING", activities=[], confirmations=[])
    async for event, data in engine.resume(task.id, approved):
        if event == "activity":
            result.activities.append(ToolActivity(**data))
        elif event == "confirmation":
            result.confirmations = data["confirmations"]
            result.status = "CONFIRMING"
        elif event == "done":
            result.message, result.status = data["message"], data["status"]
        elif event == "error":
            result.message, result.status = data["message"], "FAILED"
    return result



@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(session_id: str | None = None, db: Session = Depends(get_db)):
    query = select(Task)
    if session_id:
        query = query.where(Task.session_id == session_id).order_by(Task.created_at.asc(), Task.id.asc())
    else:
        query = query.order_by(Task.created_at.desc(), Task.id.desc()).limit(200)
    return list(db.scalars(query))


@app.get("/api/tasks/{task_id}/confirmations")
def task_confirmations(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    if task.status != "CONFIRMING" or not task.checkpoint:
        return {"task_id": task_id, "confirmations": []}
    checkpoint = json.loads(task.checkpoint)
    confirmations = [
        {"call_id": item.get("call_id"), "name": item.get("name"), "arguments": item.get("arguments", {}), "permission": "high"}
        for item in checkpoint.get("pending", [])
    ]
    return {"task_id": task_id, "confirmations": confirmations}


@app.get("/api/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db)):
    sessions = list(db.scalars(select(SessionModel).order_by(SessionModel.updated_at.desc())))
    result = []
    for session in sessions:
        last = db.scalars(select(Task).where(Task.session_id == session.id).order_by(Task.created_at.desc()).limit(1)).first()
        count = len(list(db.scalars(select(Task.id).where(Task.session_id == session.id))))
        result.append({
            "id": session.id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "task_count": count,
            "preview": last.request if last else "",
        })
    return result


@app.get("/api/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    last = db.scalars(select(Task).where(Task.session_id == session.id).order_by(Task.created_at.desc()).limit(1)).first()
    count = len(list(db.scalars(select(Task.id).where(Task.session_id == session.id))))
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "task_count": count,
        "preview": last.request if last else "",
    }



@app.post("/api/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    session = SessionModel(title=payload.title or "New conversation")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title, "created_at": session.created_at, "updated_at": session.updated_at, "task_count": 0, "preview": ""}


@app.get("/api/tasks/{task_id}/activities", response_model=list[ActivityOut])
def get_task_activities(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    return list(db.scalars(select(Activity).where(Activity.task_id == task_id).order_by(Activity.created_at.asc())))


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    for task in db.scalars(select(Task).where(Task.session_id == session_id)):
        for activity in db.scalars(select(Activity).where(Activity.task_id == task.id)):
            db.delete(activity)
        db.delete(task)
    db.delete(session)
    db.commit()



@app.get("/api/memories", response_model=list[MemoryOut])
def list_memories(db: Session = Depends(get_db)):
    return memory_service.list_all(db)


@app.post("/api/memories", response_model=MemoryOut)
def create_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    return memory_service.create(db, content=payload.content, category=payload.category)


@app.delete("/api/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    if not memory_service.delete(db, memory_id):
        raise HTTPException(404, "Memory not found")