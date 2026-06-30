from __future__ import annotations

from sqlmodel import Session

from ..models import Chapter, Novel
from .chapter_order import sort_chapters
from .web_importer import import_from_url, fetch_chapter_text


def import_web_novel(session: Session, url: str, timeout: int = 30, allow_curl_cffi: bool = True, allow_playwright: bool = False) -> Novel:
    parsed = import_from_url(url, timeout=timeout, allow_playwright=allow_playwright)

    novel = Novel(
        title=parsed.title or "Untitled",
        source_type="web",
        source_url=url,
        description=parsed.description,
    )
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


def fetch_chapter_raw(session: Session, chapter: Chapter, timeout: int = 30, allow_curl_cffi: bool = True, allow_playwright: bool = False) -> Chapter:
    if not chapter.source_url:
        return chapter
    chapter.status = "fetching"
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    try:
        text, final_url = fetch_chapter_text(chapter.source_url, timeout=timeout, allow_curl_cffi=allow_curl_cffi, allow_playwright=allow_playwright)
    except Exception:
        chapter.status = "error"
        session.add(chapter)
        session.commit()
        raise
    chapter.raw_text = text
    chapter.source_url = final_url
    chapter.status = "fetched"
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter
