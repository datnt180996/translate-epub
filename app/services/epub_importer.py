from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from ebooklib import epub, ITEM_DOCUMENT
from bs4 import BeautifulSoup
from sqlmodel import Session

from ..models import Chapter, Novel
from .chapter_cleaner import clean_html_to_text, strip_chapter_boilerplate
from .chapter_order import sort_chapters


_log = logging.getLogger(__name__)


def _try_translate_metadata(session: Session, text: str, label: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    from .providers.factory import default_provider, get_provider
    provider_name = default_provider(session)
    if not provider_name:
        return None
    try:
        provider = get_provider(session, provider_name)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Không thể khởi tạo provider để dịch %s EPUB: %s", label, exc)
        return None
    try:
        translated = provider.translate_metadata(text.strip())
    except Exception as exc:  # noqa: BLE001
        _log.warning("Dịch %s EPUB thất bại: %s", label, exc)
        return None
    return translated or None


def _try_translate_novel_title(session: Session, text: str) -> Optional[str]:
    return _try_translate_metadata(session, text, "title")


def _try_translate_novel_author(session: Session, text: str) -> Optional[str]:
    return _try_translate_metadata(session, text, "author")


def _get_item_text(book: epub.EpubBook, item) -> str:
    try:
        content = item.get_content().decode("utf-8", errors="ignore")
    except Exception:
        return ""
    soup = BeautifulSoup(content, "lxml")
    return clean_html_to_text(str(soup))


def _spine_items(book: epub.EpubBook) -> list:
    items: list = []
    for spine_id, _linear in book.spine:
        try:
            item = book.get_item_with_id(spine_id)
        except Exception:
            item = None
        if item is None and isinstance(spine_id, str) and spine_id.startswith("#"):
            try:
                item = book.get_item_with_id(spine_id[1:])
            except Exception:
                item = None
        if item is not None and item.get_type() == ITEM_DOCUMENT:
            items.append(item)
    return items


def _chapter_title_from_item(book: epub.EpubBook, item, fallback_index: int) -> str:
    name = item.get_name() or ""
    soup_title = None
    try:
        content = item.get_content().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(content, "lxml")
        if soup.title and soup.title.string:
            soup_title = soup.title.string.strip()
        for tag in ["h1", "h2", "h3"]:
            el = soup.find(tag)
            if el and el.get_text(strip=True):
                soup_title = el.get_text(strip=True)
                break
    except Exception:
        pass

    if soup_title:
        return soup_title
    toc_match = next((t for t in book.toc if getattr(t, "href", None) and t.href.split("#")[0] == name), None)
    if toc_match is not None and getattr(toc_match, "title", None):
        return toc_match.title
    return f"Chapter {fallback_index}"


def import_epub_file(session: Session, file_path: str, original_filename: Optional[str] = None) -> Novel:
    book = epub.read_epub(file_path)

    meta_title = ""
    try:
        if book.get_metadata("DC", "title"):
            meta_title = book.get_metadata("DC", "title")[0][0]
    except Exception:
        meta_title = ""
    title = (meta_title or (original_filename or os.path.basename(file_path))).strip()
    if not title:
        title = "Untitled"

    author = ""
    try:
        if book.get_metadata("DC", "creator"):
            author = book.get_metadata("DC", "creator")[0][0]
    except Exception:
        author = ""

    description = ""
    try:
        if book.get_metadata("DC", "description"):
            description = book.get_metadata("DC", "description")[0][0]
    except Exception:
        description = ""

    novel = Novel(
        title=title,
        author=author or None,
        source_type="epub",
        source_url=original_filename,
        description=description or None,
    )
    session.add(novel)
    session.commit()
    session.refresh(novel)

    translated = _try_translate_novel_title(session, novel.title)
    if translated:
        novel.translated_title = translated
        session.add(novel)
        session.commit()
        session.refresh(novel)

    if novel.author:
        translated_author = _try_translate_novel_author(session, novel.author)
        if translated_author and translated_author != novel.author:
            novel.translated_author = translated_author
            session.add(novel)
            session.commit()
            session.refresh(novel)

    items = _spine_items(book)
    raw_entries: list[tuple[str, object, str]] = []
    for i, item in enumerate(items, start=1):
        text = _get_item_text(book, item)
        if not text or len(text.strip()) < 20:
            continue
        chapter_title = _chapter_title_from_item(book, item, i)
        raw_entries.append((chapter_title, item, text))

    ordered = sort_chapters(raw_entries, title_of=lambda e: e[0])
    for index, (chapter_title, item, text) in enumerate(ordered, start=1):
        chapter = Chapter(
            novel_id=novel.id,
            index=index,
            title=chapter_title,
            source_url=item.get_name(),
            raw_text=strip_chapter_boilerplate(text, chapter_title) or text,
            status="fetched",
        )
        session.add(chapter)

    session.commit()
    session.refresh(novel)
    return novel


def import_epub_bytes(session: Session, content: bytes, original_filename: Optional[str] = None) -> Novel:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".epub")
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return import_epub_file(session, tmp.name, original_filename)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
