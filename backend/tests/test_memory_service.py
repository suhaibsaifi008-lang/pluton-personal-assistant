import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, migrate
from app.memory_service import MemoryService, memory_service
from app.models import Memory


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                id UNINDEXED,
                content,
                category
            )
        """)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()



def test_memory_service_create_and_fts_sync(memory_db):
    service = MemoryService()
    mem = service.create(memory_db, content="User prefers Python over Java", category="preference")
    assert mem.id is not None
    assert mem.content == "User prefers Python over Java"
    assert mem.category == "preference"

    # Verify FTS5 sync table has the record
    row = memory_db.connection().exec_driver_sql(
        "SELECT id, content, category FROM memories_fts WHERE id = ?", (mem.id,)
    ).fetchone()
    assert row is not None
    assert row[0] == mem.id
    assert row[1] == "User prefers Python over Java"
    assert row[2] == "preference"


def test_memory_service_delete_and_fts_sync(memory_db):
    service = MemoryService()
    mem = service.create(memory_db, content="Temporary reminder", category="todo")
    
    # Verify present
    assert len(service.list_all(memory_db)) == 1
    
    # Delete existing
    deleted = service.delete(memory_db, mem.id)
    assert deleted is True
    assert len(service.list_all(memory_db)) == 0

    # Verify FTS5 sync table no longer has the record
    row = memory_db.connection().exec_driver_sql(
        "SELECT id FROM memories_fts WHERE id = ?", (mem.id,)
    ).fetchone()
    assert row is None

    # Deleting non-existent returns False
    assert service.delete(memory_db, "non-existent-id") is False


def test_memory_service_recall_bm25_ranking(memory_db):
    service = MemoryService()
    service.create(memory_db, content="The user loves Dark Mode for the IDE", category="preference")
    service.create(memory_db, content="Project PLUTON is an autonomous AI assistant", category="project")
    service.create(memory_db, content="Antigravity is the development orchestrator", category="system")

    # Search for dark mode preference
    results = service.recall(memory_db, "dark mode preference", limit=5)
    assert len(results) >= 1
    assert "Dark Mode" in results[0]["content"]


def test_memory_service_recall_tokenized_fallback(memory_db):
    service = MemoryService()
    service.create(memory_db, content="Database is SQLite with WAL mode enabled", category="architecture")

    # Clear FTS5 table to test fallback path directly
    memory_db.connection().exec_driver_sql("DELETE FROM memories_fts")
    memory_db.commit()

    results = service.recall(memory_db, "database sqlite wal", limit=5)
    assert len(results) == 1
    assert "SQLite" in results[0]["content"]


def test_memory_service_recall_empty_and_irrelevant_queries(memory_db):
    service = MemoryService()
    service.create(memory_db, content="Configured workspace is local directory", category="env")
    service.create(memory_db, content="Uvicorn runs on port 8000", category="network")

    # Empty query returns most recent up to limit
    empty_res = service.recall(memory_db, "", limit=1)
    assert len(empty_res) == 1

    # Irrelevant query returns existing memories as fallback
    irrelevant_res = service.recall(memory_db, "quantum entanglement astrophysics", limit=5)
    assert len(irrelevant_res) == 2


def test_memory_service_list_all(memory_db):
    service = MemoryService()
    service.create(memory_db, content="Fact 1", category="note")
    service.create(memory_db, content="Fact 2", category="note")
    
    all_mems = service.list_all(memory_db)
    assert len(all_mems) == 2
    assert all_mems[0].content == "Fact 2"  # descending created_at
