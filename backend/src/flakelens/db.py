from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from flakelens.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        # Ensure the parent directory of a file-based SQLite DB exists.
        file_part = url.split("sqlite:///", 1)[-1]
        if file_part and file_part != ":memory:" and not url.endswith(":memory:"):
            Path(file_part).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Columns added after a table may already exist in a deployment. create_all()
# only creates missing tables, so these are applied via ALTER on startup.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "test_cases": {
        "quarantined_at": "TIMESTAMP",
        "quarantine_branch": "TEXT",
        "quarantine_pr_url": "TEXT",
    },
}


def apply_additive_migrations(target_engine) -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(target_engine)
    with target_engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
