from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict

from sqlmodel import Session

from ..db import engine
from ..models import Chapter, Novel
from .glossary_service import translate_chapter


@dataclass
class _RunningTask:
    chapter_id: int
    novel_id: int
    provider: str
    thread: threading.Thread


_tasks: Dict[int, _RunningTask] = {}
_lock = threading.Lock()


def is_translating(chapter_id: int) -> bool:
    with _lock:
        t = _tasks.get(chapter_id)
        return t is not None and t.thread.is_alive()


def _worker(novel_id: int, chapter_id: int, provider_name: str) -> None:
    try:
        with Session(engine) as session:
            novel = session.get(Novel, novel_id)
            chapter = session.get(Chapter, chapter_id)
            if novel is None or chapter is None:
                return
            translate_chapter(session, novel, chapter, provider_name=provider_name)
    except Exception as e:  # noqa: BLE001
        try:
            with Session(engine) as session:
                chapter = session.get(Chapter, chapter_id)
                if chapter is not None:
                    chapter.status = "error"
                    chapter.translation_provider = chapter.translation_provider or provider_name
                    session.add(chapter)
                    session.commit()
        except Exception:
            pass
        _last_errors[chapter_id] = str(e)
    finally:
        with _lock:
            _tasks.pop(chapter_id, None)


_last_errors: Dict[int, str] = {}


def get_last_error(chapter_id: int) -> str | None:
    return _last_errors.pop(chapter_id, None)


def start_translation(novel_id: int, chapter_id: int, provider_name: str) -> bool:
    with _lock:
        existing = _tasks.get(chapter_id)
        if existing is not None and existing.thread.is_alive():
            return False
        thread = threading.Thread(
            target=_worker,
            args=(novel_id, chapter_id, provider_name),
            daemon=True,
        )
        _tasks[chapter_id] = _RunningTask(
            chapter_id=chapter_id,
            novel_id=novel_id,
            provider=provider_name,
            thread=thread,
        )
        thread.start()
        return True