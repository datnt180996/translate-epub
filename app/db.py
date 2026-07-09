from __future__ import annotations

import os
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine, text

from .config import get_settings


_settings = get_settings()


def _engine():
    url = _settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=False, connect_args=connect_args)


engine = _engine()


_SCHEMA_PATCHES: dict[str, dict[str, str]] = {
    "chapter": {
        "error_message": "TEXT",
        "translation_warning": "TEXT",
        "translated_title": "TEXT",
        "failed_translation_draft": "TEXT",
    },
    "novel": {
        "translated_title": "TEXT",
        "cover_url": "TEXT",
        "translated_author": "TEXT",
    },
    "translationjob": {
        "novel_id": "INTEGER",
        "provider": "TEXT",
        "status": "TEXT",
        "total_chunks": "INTEGER",
        "done_chunks": "INTEGER",
        "failed_chunks": "INTEGER",
        "current_chunk": "INTEGER",
        "error_message": "TEXT",
        "started_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
    "appsetting": {
        "value": "TEXT",
        "updated_at": "TIMESTAMP",
    },
}


def _apply_schema_patches() -> None:
    if not _settings.database_url.startswith("sqlite"):
        return
    db_path = _settings.database_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return
    with engine.connect() as conn:
        for table, cols in _SCHEMA_PATCHES.items():
            try:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            except Exception:
                continue
            if not rows:
                # table does not exist; create_all will create it
                continue
            existing = {row[1] for row in rows}
            for col, decl in cols.items():
                if col in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))
        conn.commit()


def init_db() -> None:
    os.makedirs(os.path.dirname(_settings.database_url.replace("sqlite:///", "")) or ".", exist_ok=True)
    from . import models  # noqa: F401  ensure all SQLModel classes are registered
    SQLModel.metadata.create_all(engine)
    _apply_schema_patches()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
