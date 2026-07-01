from __future__ import annotations

import os
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings


_settings = get_settings()


def _engine():
    url = _settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=False, connect_args=connect_args)


engine = _engine()


def init_db() -> None:
    os.makedirs(os.path.dirname(_settings.database_url.replace("sqlite:///", "")) or ".", exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
