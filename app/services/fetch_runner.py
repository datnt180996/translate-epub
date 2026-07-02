from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from sqlmodel import Session, select

from ..config import get_settings
from ..db import engine
from ..models import Chapter, Novel
from .web_importer import fetch_chapter_text


_log = logging.getLogger(__name__)


@dataclass
class _RunningFetchTask:
    novel_id: int
    thread: threading.Thread


_tasks: Dict[int, _RunningFetchTask] = {}
_lock = threading.Lock()


def is_fetching_novel(novel_id: int) -> bool:
    with _lock:
        t = _tasks.get(novel_id)
        return t is not None and t.thread.is_alive()


def _safe_get_settings():
    try:
        return get_settings()
    except Exception:  # noqa: BLE001
        return None


def _claim_chapters(novel_id: int, batch_size: int) -> list[tuple[int, str]]:
    """Pick chapters in idle/pending/error states that still need raw_text.

    Returns primitive (chapter_id, source_url) tuples so worker threads do not
    share ORM instances with the calling session.
    """
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(Chapter)
                .where(Chapter.novel_id == novel_id)
                .order_by(Chapter.index)
            ).all()
        )
        pending: list[tuple[int, str]] = []
        for ch in rows:
            if not ch.source_url:
                continue
            if ch.raw_text:
                continue
            if ch.status in ("translating",):
                continue
            pending.append((ch.id, ch.source_url))
            if len(pending) >= batch_size:
                break
    return pending


def _mark_fetching(chapter_id: int) -> None:
    with Session(engine) as session:
        ch = session.get(Chapter, chapter_id)
        if ch is None:
            return
        ch.status = "fetching"
        ch.error_message = None
        ch.updated_at = datetime.utcnow()
        session.add(ch)
        session.commit()


def _mark_fetched(chapter_id: int, text: str, final_url: str) -> None:
    with Session(engine) as session:
        ch = session.get(Chapter, chapter_id)
        if ch is None:
            return
        ch.raw_text = text
        ch.source_url = final_url
        ch.status = "fetched"
        ch.error_message = None
        ch.updated_at = datetime.utcnow()
        session.add(ch)
        session.commit()


def _mark_error(chapter_id: int, message: str) -> None:
    with Session(engine) as session:
        ch = session.get(Chapter, chapter_id)
        if ch is None:
            return
        ch.status = "error"
        ch.error_message = message
        ch.updated_at = datetime.utcnow()
        session.add(ch)
        session.commit()


def _novel_exists(novel_id: int) -> bool:
    with Session(engine) as session:
        return session.get(Novel, novel_id) is not None


def _fetch_one_with_text(
    chapter_id: int,
    source_url: str,
    timeout: int,
    allow_curl_cffi: bool,
    allow_playwright: bool,
    max_retries: int,
    delay: float,
) -> tuple[int, bool, str, str]:
    """Returns (chapter_id, ok, final_url, text_or_error)."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            text, final_url = fetch_chapter_text(
                source_url,
                timeout=timeout,
                allow_curl_cffi=allow_curl_cffi,
                allow_playwright=allow_playwright,
            )
            if not text or not text.strip():
                raise RuntimeError("fetch_chapter_text trả về nội dung rỗng")
            return chapter_id, True, final_url or source_url, text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < max_retries:
                time.sleep(delay * (2 ** attempt))
                continue
            break
    return chapter_id, False, source_url, str(last_error) if last_error else "Unknown error"


def _worker_v2(novel_id: int) -> None:
    try:
        settings = _safe_get_settings()
        timeout = int(getattr(settings, "request_timeout", 30) or 30)
        allow_curl_cffi = bool(getattr(settings, "use_curl_cffi_fallback", True))
        allow_playwright = bool(getattr(settings, "use_playwright_fallback", False))
        max_retries = int(getattr(settings, "fetch_max_retries", 2) or 2)
        delay = float(getattr(settings, "fetch_request_delay", 0.3) or 0.0)
        batch_size = max(1, int(getattr(settings, "fetch_batch_size", 50) or 50))
        concurrency = max(1, int(getattr(settings, "fetch_concurrency", 3) or 3))

        while True:
            if not _novel_exists(novel_id):
                return
            claimed = _claim_chapters(novel_id, batch_size)
            if not claimed:
                return

            for cid, _url in claimed:
                try:
                    _mark_fetching(cid)
                except Exception:
                    pass

            with ThreadPoolExecutor(max_workers=min(concurrency, len(claimed))) as pool:
                futures = [
                    pool.submit(
                        _fetch_one_with_text,
                        cid,
                        url,
                        timeout,
                        allow_curl_cffi,
                        allow_playwright,
                        max_retries,
                        delay,
                    )
                    for cid, url in claimed
                ]
                for fut in as_completed(futures):
                    try:
                        cid, ok, final_url, payload = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        _log.warning("Fetch worker future lỗi: %s", exc)
                        continue
                    if ok:
                        _mark_fetched(cid, payload, final_url)
                    else:
                        _mark_error(cid, payload)

            if delay > 0:
                time.sleep(delay)
    except Exception as exc:  # noqa: BLE001
        _log.exception("Background fetch-all novel_id=%s thất bại: %s", novel_id, exc)
    finally:
        with _lock:
            _tasks.pop(novel_id, None)


def start_fetch_all(novel_id: int) -> bool:
    """Start a background fetch-all job for the given novel.

    Returns False if a job is already running for this novel.
    """
    with _lock:
        existing = _tasks.get(novel_id)
        if existing is not None and existing.thread.is_alive():
            return False
        thread = threading.Thread(
            target=_worker_v2,
            args=(novel_id,),
            daemon=True,
        )
        _tasks[novel_id] = _RunningFetchTask(novel_id=novel_id, thread=thread)
        thread.start()
        return True


def cleanup_stale_fetching() -> int:
    """Reset chapters stuck in 'fetching' from interrupted jobs.

    Called on startup since the in-memory registry does not survive restarts.
    Returns the number of rows reset.
    """
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(Chapter).where(Chapter.status == "fetching")
            ).all()
        )
        reset = 0
        for ch in rows:
            if ch.raw_text:
                ch.status = "fetched"
                ch.error_message = None
            else:
                ch.status = "pending"
                ch.error_message = "App đã restart trong khi đang tải. Vui lòng thử lại."
                ch.updated_at = datetime.utcnow()
                session.add(ch)
                reset += 1
        if reset:
            session.commit()
    return reset
