from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite:///"):
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate():
    """Lightweight additive migration for databases created before columns/tables were added."""
    with engine.begin() as connection:
        if settings.database_url.startswith("sqlite"):
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.exec_driver_sql("PRAGMA busy_timeout=5000")

        # Ensure task columns
        rows = connection.exec_driver_sql("PRAGMA table_info(tasks)").all()
        columns = {row[1] for row in rows}
        if columns:
            if "session_id" not in columns:
                connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN session_id VARCHAR")
            if "checkpoint" not in columns:
                connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN checkpoint TEXT")

        # Ensure activities table exists
        connection.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS activities (
                id VARCHAR PRIMARY KEY,
                task_id VARCHAR,
                name VARCHAR(120),
                summary TEXT,
                status VARCHAR(40),
                arguments TEXT,
                result TEXT,
                created_at DATETIME
            )
        """)
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_activities_task_id ON activities(task_id)")

        # Ensure memories_fts FTS5 virtual table exists and is populated
        if settings.database_url.startswith("sqlite"):
            try:
                connection.exec_driver_sql("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                        id UNINDEXED,
                        content,
                        category
                    )
                """)
                # Populate existing rows if fts is empty
                fts_count = connection.exec_driver_sql("SELECT count(*) FROM memories_fts").scalar()
                mem_count = connection.exec_driver_sql("SELECT count(*) FROM memories").scalar()
                if fts_count == 0 and mem_count > 0:
                    connection.exec_driver_sql("""
                        INSERT INTO memories_fts (id, content, category)
                        SELECT id, content, category FROM memories
                    """)
            except Exception:
                pass



def reconcile_stale_tasks():
    """Find and transition transient tasks left in indeterminate states on startup."""
    import json
    from sqlalchemy import select
    from .models import Activity, Task, TaskStatus

    from .kernel.control_kernel import KERNEL
    from .kernel.task_registry import ACTIVE_TASK_REGISTRY

    # Ensure kernel is in clean revoked state on startup
    KERNEL.emergency_stop()
    ACTIVE_TASK_REGISTRY.purge_all(reason="startup_reconciliation")

    with SessionLocal() as db:
        non_terminal_statuses = [
            TaskStatus.RUNNING.value,
            "EXECUTING",
            "VERIFYING",
            "WAITING",
            "AWAITING_APPROVAL",
        ]
        stale_tasks = list(db.scalars(select(Task).where(Task.status.in_(non_terminal_statuses))))
        for task in stale_tasks:
            task.status = TaskStatus.FAILED.value
            if not task.response:
                task.response = "Task interrupted: server stopped or restarted during execution."
            activity = Activity(
                task_id=task.id,
                name="system.reconciliation",
                summary="Stale task marked as failed during server startup reconciliation.",
                status="failed",
                result=json.dumps({"reason": "Server restarted while task was in non-terminal state"}),
            )
            db.add(activity)

        confirming_tasks = list(db.scalars(select(Task).where(Task.status == TaskStatus.CONFIRMING.value)))
        for task in confirming_tasks:
            is_valid_checkpoint = False
            if task.checkpoint:
                try:
                    data = json.loads(task.checkpoint)
                    if data.get("pending"):
                        is_valid_checkpoint = True
                except Exception:
                    is_valid_checkpoint = False
            if not is_valid_checkpoint:
                task.status = TaskStatus.FAILED.value
                task.response = "Confirmation checkpoint corrupted or missing upon server restart."
                activity = Activity(
                    task_id=task.id,
                    name="system.reconciliation",
                    summary="Corrupted confirmation marked as failed during startup reconciliation.",
                    status="failed",
                    result=json.dumps({"reason": "Invalid or missing checkpoint"}),
                )
                db.add(activity)

        db.commit()


