import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


def test_health_endpoint():
    async def health_check():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/api/health")

    response = asyncio.run(health_check())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["name"] == "PLUTON AI"


def test_provider_status_does_not_expose_credentials():
    async def settings_check():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/api/settings/status")

    response = asyncio.run(settings_check())
    assert response.status_code == 200
    assert set(response.json()) == {"provider", "model", "configured", "supports_vision"}


def test_provider_status_reports_freellmapi_configured(monkeypatch):
    from app.config import Settings
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(ai_provider="freeLLMAPI", freeLLMAPI_api_key="valid-key", freeLLMAPI_model="auto"))

    async def check():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/api/settings/status")

    response = asyncio.run(check())
    assert response.status_code == 200
    assert response.json() == {"provider": "freeLLMAPI", "model": "auto", "configured": True, "supports_vision": True}


def test_provider_status_reports_freellmapi_unconfigured(monkeypatch):
    from app.config import Settings
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(ai_provider="freeLLMAPI", freeLLMAPI_api_key=None, freeLLMAPI_model="auto"))

    async def check():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/api/settings/status")

    response = asyncio.run(check())
    assert response.status_code == 200
    assert response.json() == {"provider": "freeLLMAPI", "model": "auto", "configured": False, "supports_vision": False}




def test_tools_endpoint_lists_registry():
    async def tools_check():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/api/tools")

    response = asyncio.run(tools_check())
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "filesystem.read" in names
    assert "filesystem.write" in names
    assert "terminal.run" in names
    assert "web.search" in names
    assert "web.fetch" in names
    assert "memory.recall" in names
    assert "memory.save" in names
    terminal = next(item for item in response.json() if item["name"] == "terminal.run")
    assert terminal["permission"] == "high"


def test_chat_reports_missing_provider_configuration(monkeypatch):
    from app.config import Settings
    monkeypatch.setattr("app.agent.get_settings", lambda: Settings(ai_provider="openai", openai_api_key=None))
    monkeypatch.setattr("app.providers.get_settings", lambda: Settings(ai_provider="openai", openai_api_key=None))

    async def chat_request():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.post("/api/chat", json={"message": "Hello"})

    response = asyncio.run(chat_request())
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert "No AI provider key" in response.json()["message"]


def test_chat_stream_returns_sse():
    async def chat_stream():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.post("/api/chat", json={"message": "Hello", "stream": True})

    response = asyncio.run(chat_stream())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: task" in response.text
    assert "event: done" in response.text or "event: error" in response.text



def test_session_lifecycle():
    async def flow():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                created = await client.post("/api/sessions", json={"title": "My session"})
                assert created.status_code == 200
                session_id = created.json()["id"]

                # Get session by ID
                single = await client.get(f"/api/sessions/{session_id}")
                assert single.status_code == 200
                assert single.json()["id"] == session_id
                assert single.json()["title"] == "My session"

                listed = await client.get("/api/sessions")
                assert listed.status_code == 200
                assert any(item["id"] == session_id for item in listed.json())

                chat = await client.post("/api/chat", json={"message": "Hello", "session_id": session_id})
                assert chat.json()["session_id"] == session_id

                tasks = await client.get("/api/tasks", params={"session_id": session_id})
                assert tasks.status_code == 200
                assert len(tasks.json()) == 1

                deleted = await client.delete(f"/api/sessions/{session_id}")
                assert deleted.status_code == 204

                # Ensure 404 after deletion
                single_after = await client.get(f"/api/sessions/{session_id}")
                assert single_after.status_code == 404

                after = await client.get("/api/sessions")
                assert all(item["id"] != session_id for item in after.json())

    asyncio.run(flow())


def test_session_tasks_chronological_ordering():
    from app.database import SessionLocal
    from app.models import Session as SessionModel, Task

    async def check():
        db = SessionLocal()
        s = SessionModel(title="Multi-turn conversation")
        db.add(s)
        db.commit()
        db.refresh(s)
        s_id = str(s.id)

        t1 = Task(session_id=s_id, title="Turn 1", request="First question", response="First answer", status="COMPLETED")
        db.add(t1)
        db.commit()

        t2 = Task(session_id=s_id, title="Turn 2", request="Second question", response="Second answer", status="COMPLETED")
        db.add(t2)
        db.commit()

        t3 = Task(session_id=s_id, title="Turn 3", request="Third question", response="Third answer", status="COMPLETED")
        db.add(t3)
        db.commit()
        db.close()

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/tasks", params={"session_id": s_id})
                assert res.status_code == 200
                tasks = res.json()
                assert len(tasks) == 3
                # Must be strictly chronological ascending: First -> Second -> Third
                assert tasks[0]["request"] == "First question"
                assert tasks[1]["request"] == "Second question"
                assert tasks[2]["request"] == "Third question"

    asyncio.run(check())


def test_switch_and_retrieve_multiple_sessions():
    from app.database import SessionLocal
    from app.models import Session as SessionModel, Task

    async def check():
        db = SessionLocal()
        s1 = SessionModel(title="Session A")
        s2 = SessionModel(title="Session B")
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        s1_id = str(s1.id)
        s2_id = str(s2.id)

        t_a = Task(session_id=s1_id, title="Task A", request="Message in A", response="Answer in A", status="COMPLETED")
        t_b = Task(session_id=s2_id, title="Task B", request="Message in B", response="Answer in B", status="COMPLETED")
        db.add_all([t_a, t_b])
        db.commit()
        db.close()

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Query Session A
                res_a = await client.get("/api/tasks", params={"session_id": s1_id})
                assert res_a.status_code == 200
                assert len(res_a.json()) == 1
                assert res_a.json()[0]["request"] == "Message in A"

                # Query Session B
                res_b = await client.get("/api/tasks", params={"session_id": s2_id})
                assert res_b.status_code == 200
                assert len(res_b.json()) == 1
                assert res_b.json()[0]["request"] == "Message in B"

    asyncio.run(check())




def test_approve_and_deny_validate_state():
    async def flow():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                missing = await client.post("/api/tasks/does-not-exist/approve")
                assert missing.status_code == 404

                confirmations = await client.get("/api/tasks/does-not-exist/confirmations")
                assert confirmations.status_code == 404

                chat = await client.post("/api/chat", json={"message": "Hello"})
                task_id = chat.json()["task_id"]

                # Task failed with no provider configured, so it is not CONFIRMING.
                conflict = await client.post(f"/api/tasks/{task_id}/approve")
                assert conflict.status_code == 409

                pending = await client.get(f"/api/tasks/{task_id}/confirmations")
                assert pending.json()["confirmations"] == []

    asyncio.run(flow())


def test_memory_crud():
    async def flow():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                created = await client.post("/api/memories", json={"content": "I prefer concise answers", "category": "preference"})
                assert created.status_code == 200
                memory_id = created.json()["id"]

                listed = await client.get("/api/memories")
                assert any(item["id"] == memory_id for item in listed.json())

                deleted = await client.delete(f"/api/memories/{memory_id}")
                assert deleted.status_code == 204

                after = await client.get("/api/memories")
                assert all(item["id"] != memory_id for item in after.json())

    asyncio.run(flow())


def test_drain_engine_helper_consumes_generator(monkeypatch):
    from app.main import _drain_engine
    from app.providers.base import AIProvider, ProviderRequest, ProviderResponse
    from app.database import SessionLocal
    from app.models import Task, Session as SessionModel

    class DummyProvider(AIProvider):
        name = "dummy"
        @property
        def model(self): return "dummy-model"
        async def respond(self, request: ProviderRequest) -> ProviderResponse:
            return ProviderResponse("resp-1", "Executed successfully")

    monkeypatch.setattr("app.agent.create_provider", lambda s=None: DummyProvider())

    with SessionLocal() as db:
        sess = SessionModel(title="Drain Test")
        db.add(sess)
        db.commit()
        task = Task(session_id=sess.id, title="Test", request="Hello", status="CREATED")
        db.add(task)
        db.commit()
        task_id = task.id

    asyncio.run(_drain_engine(task_id))

    with SessionLocal() as db:
        updated = db.get(Task, task_id)
        assert updated.status == "COMPLETED"
        assert updated.response == "Executed successfully"


def test_non_streaming_chat_executes_task_to_completion(monkeypatch):
    from app.providers.base import AIProvider, ProviderRequest, ProviderResponse

    class DummyProvider(AIProvider):
        name = "dummy"
        @property
        def model(self): return "dummy-model"
        async def respond(self, request: ProviderRequest) -> ProviderResponse:
            return ProviderResponse("resp-non-stream", "Non-streaming completed response")

    monkeypatch.setattr("app.agent.create_provider", lambda s=None: DummyProvider())

    async def flow():
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post("/api/chat", json={"message": "What is the date?", "stream": False})
                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "COMPLETED"
                assert data["message"] == "Non-streaming completed response"

    asyncio.run(flow())