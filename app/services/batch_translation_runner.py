from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from sqlmodel import Session, select

from ..db import engine
from ..models import Chapter, Novel
from .glossary_service import translate_chapter


_log = logging.getLogger(__name__)


@dataclass
class _RunningBatchTask:
    novel_id: int
    chapter_ids: List[int]
    provider: str
    thread: threading.Thread
    current_chapter_id: Optional[int] = None


_tasks: Dict[int, _RunningBatchTask] = {}
_lock = threading.Lock()


def is_batch_translating_novel(novel_id: int) -> bool:
    with _lock:
        t = _tasks.get(novel_id)
        return t is not None and t.thread.is_alive()


def get_batch_state(novel_id: int) -> Optional[dict]:
    """Return a snapshot of the currently running batch for a novel, or None."""
    with _lock:
        t = _tasks.get(novel_id)
        if t is None or not t.thread.is_alive():
            return None
        current_chapter_id = t.current_chapter_id
        if current_chapter_id in t.chapter_ids:
            current_index = t.chapter_ids.index(current_chapter_id)
            queued_chapter_ids = t.chapter_ids[current_index + 1 :]
        else:
            queued_chapter_ids = list(t.chapter_ids)
        return {
            "chapter_ids": list(t.chapter_ids),
            "current_chapter_id": current_chapter_id,
            "queued_chapter_ids": queued_chapter_ids,
            "provider": t.provider,
        }


def _is_eligible_for_batch(chapter: Chapter) -> bool:
    """Eligibility rules shared by route, worker and tests.

    A chapter is eligible if it has raw text, no translated text, and is not
    already in an active fetching/translating state.
    """
    if not chapter.raw_text:
        return False
    if chapter.translated_text:
        return False
    if chapter.status in ("fetching", "translating"):
        return False
    return True


def filter_eligible_for_novel(novel_id: int, candidate_ids: Iterable[int]) -> List[int]:
    """Filter a list of chapter IDs down to those eligible for batch translation.

    Ordering is by chapter index ascending.
    """
    candidates = {int(i) for i in candidate_ids if i}
    if not candidates:
        return []
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(Chapter)
                .where(Chapter.novel_id == novel_id)
                .where(Chapter.id.in_(candidates))
            ).all()
        )
        eligible: list[int] = []
        for ch in rows:
            if ch.id not in candidates:
                continue
            if _is_eligible_for_batch(ch):
                eligible.append(ch.id)
        eligible.sort(key=lambda cid: next(c.index for c in rows if c.id == cid))
    return eligible


def eligible_count_for_novel(novel_id: int) -> int:
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(Chapter).where(Chapter.novel_id == novel_id)
            ).all()
        )
    return sum(1 for c in rows if _is_eligible_for_batch(c))


def _mark_error_chapter(chapter_id: int, message: str) -> None:
    with Session(engine) as session:
        ch = session.get(Chapter, chapter_id)
        if ch is None:
            return
        ch.status = "error"
        ch.error_message = message
        ch.updated_at = datetime.utcnow()
        session.add(ch)
        session.commit()


def _worker(novel_id: int, chapter_ids: List[int], provider_name: str) -> None:
    from . import translation_jobs as jobs

    ordered_ids = filter_eligible_for_novel(novel_id, chapter_ids)
    try:
        for cid in ordered_ids:
            if not is_batch_translating_novel(novel_id):
                return
            with _lock:
                task = _tasks.get(novel_id)
                if task is not None:
                    task.current_chapter_id = cid
            with Session(engine) as session:
                novel = session.get(Novel, novel_id)
                chapter = session.get(Chapter, cid)
                if novel is None or chapter is None or chapter.novel_id != novel_id:
                    continue
                if not _is_eligible_for_batch(chapter):
                    continue
            try:
                with Session(engine) as session:
                    jobs.reset(
                        session,
                        cid,
                        novel_id=novel_id,
                        provider=provider_name,
                    )
                with Session(engine) as session:
                    novel = session.get(Novel, novel_id)
                    chapter = session.get(Chapter, cid)
                    if novel is None or chapter is None or chapter.novel_id != novel_id:
                        continue
                    if not _is_eligible_for_batch(chapter):
                        continue
                    chapter.status = "translating"
                    chapter.translation_provider = provider_name
                    chapter.updated_at = datetime.utcnow()
                    session.add(chapter)
                    session.commit()
                with Session(engine) as session:
                    novel = session.get(Novel, novel_id)
                    chapter = session.get(Chapter, cid)
                    if novel is None or chapter is None or chapter.novel_id != novel_id:
                        continue
                    translate_chapter(
                        session,
                        novel,
                        chapter,
                        provider_name=provider_name,
                    )
            except Exception as exc:  # noqa: BLE001
                _log.warning("Batch translate chapter %s thất bại: %s", cid, exc)
                _mark_error_chapter(cid, str(exc))
                continue
    except Exception as exc:  # noqa: BLE001
        _log.exception("Batch translate novel_id=%s thất bại: %s", novel_id, exc)
    finally:
        with _lock:
            existing = _tasks.get(novel_id)
            if existing is not None and existing.chapter_ids == list(chapter_ids):
                _tasks.pop(novel_id, None)


def start_batch_translation(
    novel_id: int, chapter_ids: List[int], provider_name: str
) -> tuple[bool, int]:
    """Start a sequential batch translation job for a novel.

    Returns ``(started, eligible_count)``. ``started`` is False if a batch is
    already running for the novel.
    """
    with _lock:
        existing = _tasks.get(novel_id)
        if existing is not None and existing.thread.is_alive():
            return False, 0
    eligible_ids = filter_eligible_for_novel(novel_id, chapter_ids)
    if not eligible_ids:
        return True, 0
    with _lock:
        existing = _tasks.get(novel_id)
        if existing is not None and existing.thread.is_alive():
            return False, len(eligible_ids)
        thread = threading.Thread(
            target=_worker,
            args=(novel_id, eligible_ids, provider_name),
            daemon=True,
        )
        _tasks[novel_id] = _RunningBatchTask(
            novel_id=novel_id,
            chapter_ids=list(eligible_ids),
            provider=provider_name,
            thread=thread,
        )
        thread.start()
    return True, len(eligible_ids)


def cleanup_stale_translating() -> int:
    """Reset chapters stuck in 'translating' from interrupted jobs.

    Called on startup since the in-memory registries do not survive restarts.
    Returns the number of chapters reset to 'error'.
    """
    reset = 0
    with Session(engine) as session:
        rows = list(
            session.exec(select(Chapter).where(Chapter.status == "translating")).all()
        )
        for ch in rows:
            if ch.translated_text:
                continue
            ch.status = "error"
            ch.error_message = "App đã restart trong khi đang dịch. Vui lòng thử lại."
            ch.updated_at = datetime.utcnow()
            session.add(ch)
            reset += 1
        if reset:
            session.commit()
    return reset
