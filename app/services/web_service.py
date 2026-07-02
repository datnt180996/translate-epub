from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session

from ..config import get_settings
from ..models import Chapter, Novel
from .chapter_cleaner import strip_chapter_boilerplate
from .chapter_order import sort_chapters
from .providers.factory import default_provider, get_provider
from .web_importer import import_from_url, fetch_chapter_text


_log = logging.getLogger(__name__)


def _fetch_settings() -> dict:
    try:
        s = get_settings()
        return {
            "timeout": int(getattr(s, "request_timeout", 30) or 30),
            "allow_curl_cffi": bool(getattr(s, "use_curl_cffi_fallback", True)),
            "allow_playwright": bool(getattr(s, "use_playwright_fallback", False)),
        }
    except Exception:  # noqa: BLE001
        return {"timeout": 30, "allow_curl_cffi": True, "allow_playwright": False}


def _try_translate_metadata(session: Session, text: str, label: str) -> Optional[str]:
    """Try to translate a short metadata string (title/author) using the default provider.

    Returns the translated string on success, or ``None`` if no provider is
    configured, the translation fails, or the result is not usable. Failures
    are logged but never raised so imports stay non-blocking.
    """
    if not text or not text.strip():
        return None
    provider_name = default_provider(session)
    if not provider_name:
        return None
    try:
        provider = get_provider(session, provider_name)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Không thể khởi tạo provider để dịch %s: %s", label, exc)
        return None
    try:
        translated = provider.translate_metadata(text.strip())
    except Exception as exc:  # noqa: BLE001
        _log.warning("Dịch %s thất bại: %s", label, exc)
        return None
    if not translated:
        return None
    return translated


def _try_translate_title(session: Session, text: str) -> Optional[str]:
    return _try_translate_metadata(session, text, "title")


def _try_translate_author(session: Session, text: str) -> Optional[str]:
    return _try_translate_metadata(session, text, "author")


def import_web_novel(session: Session, url: str, timeout: Optional[int] = None, allow_curl_cffi: Optional[bool] = None, allow_playwright: Optional[bool] = None) -> Novel:
    cfg = _fetch_settings()
    if timeout is None:
        timeout = cfg["timeout"]
    if allow_curl_cffi is None:
        allow_curl_cffi = cfg["allow_curl_cffi"]
    if allow_playwright is None:
        allow_playwright = cfg["allow_playwright"]
    parsed = import_from_url(
        url,
        timeout=timeout,
        allow_curl_cffi=allow_curl_cffi,
        allow_playwright=allow_playwright,
    )

    novel = Novel(
        title=parsed.title or "Untitled",
        source_type="web",
        source_url=url,
        description=parsed.description,
        author=parsed.author,
        cover_url=parsed.cover_url,
    )
    session.add(novel)
    session.commit()
    session.refresh(novel)

    translated = _try_translate_title(session, novel.title)
    if translated:
        novel.translated_title = translated
        session.add(novel)
        session.commit()
        session.refresh(novel)

    if novel.author:
        translated_author = _try_translate_author(session, novel.author)
        if translated_author and translated_author != novel.author:
            novel.translated_author = translated_author
            session.add(novel)
            session.commit()
            session.refresh(novel)

    ordered = sort_chapters(parsed.chapters, title_of=lambda c: c.title)
    for idx, ch in enumerate(ordered, start=1):
        chapter = Chapter(
            novel_id=novel.id,
            index=idx,
            title=ch.title,
            source_url=ch.url,
            status="pending",
        )
        session.add(chapter)

    session.commit()
    session.refresh(novel)
    return novel


def fetch_chapter_raw(session: Session, chapter: Chapter, timeout: Optional[int] = None, allow_curl_cffi: Optional[bool] = None, allow_playwright: Optional[bool] = None) -> Chapter:
    if not chapter.source_url:
        return chapter
    cfg = _fetch_settings()
    if timeout is None:
        timeout = cfg["timeout"]
    if allow_curl_cffi is None:
        allow_curl_cffi = cfg["allow_curl_cffi"]
    if allow_playwright is None:
        allow_playwright = cfg["allow_playwright"]
    chapter.status = "fetching"
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    try:
        text, final_url = fetch_chapter_text(
            chapter.source_url,
            timeout=timeout,
            allow_curl_cffi=allow_curl_cffi,
            allow_playwright=allow_playwright,
        )
    except Exception:
        chapter.status = "error"
        session.add(chapter)
        session.commit()
        raise
    chapter.raw_text = strip_chapter_boilerplate(text, chapter.title) or text
    chapter.source_url = final_url
    chapter.status = "fetched"
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter
