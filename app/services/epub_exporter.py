from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
import re
import unicodedata
import uuid

from ebooklib import epub
from sqlmodel import Session, select

from ..models import Chapter, Novel


class EpubExportError(ValueError):
    pass


@dataclass(frozen=True)
class EpubExportResult:
    content: bytes
    filename: str
    chapter_count: int


_EPUB_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.7;
  margin: 5%;
  color: #1f2933;
}
h1 {
  font-size: 1.45em;
  line-height: 1.35;
  margin: 0 0 1.2em;
}
p {
  margin: 0 0 0.9em;
  text-align: justify;
}
""".strip()


def _display_title(novel: Novel) -> str:
    return (novel.translated_title or novel.title or "Untitled").strip() or "Untitled"


def _display_author(novel: Novel) -> str:
    return (novel.translated_author or novel.author or "").strip()


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "ebook"


def _preview_indices(indices: list[int], limit: int = 12) -> str:
    shown = ", ".join(str(i) for i in indices[:limit])
    if len(indices) > limit:
        shown += f", ... (+{len(indices) - limit})"
    return shown


def _normalized_line(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().casefold()
    return re.sub(r"\s+", " ", value)


def _is_source_metadata_line(line: str) -> bool:
    text = _normalized_line(line)
    return bool(
        re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text)
        or re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}", text)
        or re.match(r"^(tác giả|tac gia|author)\s*[:：]", text)
    )


def _is_chapter_heading_line(line: str, chapter_index: int) -> bool:
    text = _normalized_line(line)
    return bool(re.match(rf"^(chương|chuong|chapter)\s*0*{chapter_index}\b", text))


def _clean_export_paragraphs(text: str, title_variants: list[str], chapter_index: int) -> list[str]:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    title_set = {_normalized_line(title) for title in title_variants if title and title.strip()}
    while paragraphs:
        first = paragraphs[0]
        normalized_first = _normalized_line(first)
        if (
            normalized_first in title_set
            or _is_chapter_heading_line(first, chapter_index)
            or _is_source_metadata_line(first)
        ):
            paragraphs.pop(0)
            continue
        break
    return paragraphs


def _chapter_body(title: str, text: str, title_variants: list[str], chapter_index: int) -> str:
    paragraphs = _clean_export_paragraphs(text, title_variants, chapter_index)
    body = "\n".join(f"<p>{escape(line)}</p>" for line in paragraphs)
    return f"<h1>{escape(title)}</h1>\n{body}"


def export_translated_range(
    session: Session,
    novel: Novel,
    from_index: int,
    to_index: int,
) -> EpubExportResult:
    if from_index < 1 or to_index < 1:
        raise EpubExportError("Số chương phải lớn hơn 0.")
    if from_index > to_index:
        raise EpubExportError("Chương bắt đầu phải nhỏ hơn hoặc bằng chương kết thúc.")

    chapters = list(
        session.exec(
            select(Chapter)
            .where(
                Chapter.novel_id == novel.id,
                Chapter.index >= from_index,
                Chapter.index <= to_index,
            )
            .order_by(Chapter.index)
        ).all()
    )
    if not chapters:
        raise EpubExportError(f"Không tìm thấy chương nào trong khoảng {from_index}-{to_index}.")

    existing_indices = {chapter.index for chapter in chapters}
    missing_indices = [i for i in range(from_index, to_index + 1) if i not in existing_indices]
    if missing_indices:
        raise EpubExportError(
            "Thiếu dữ liệu chương trong khoảng đã chọn: " + _preview_indices(missing_indices)
        )

    untranslated = [
        chapter.index
        for chapter in chapters
        if not chapter.translated_text or not chapter.translated_text.strip()
    ]
    if untranslated:
        raise EpubExportError(
            "Khoảng đã chọn có chương chưa dịch: " + _preview_indices(untranslated)
        )

    book = epub.EpubBook()
    title = _display_title(novel)
    range_label = f"{from_index}-{to_index}"
    book.set_identifier(f"ebook-translator-{novel.id}-{range_label}-{uuid.uuid4()}")
    book.set_title(f"{title} ({range_label})")
    book.set_language("vi")
    author = _display_author(novel)
    if author:
        book.add_author(author)
    if novel.description:
        book.add_metadata("DC", "description", novel.description)

    style = epub.EpubItem(
        uid="reader_css",
        file_name="style/reader.css",
        media_type="text/css",
        content=_EPUB_CSS.encode("utf-8"),
    )
    book.add_item(style)

    epub_chapters: list[epub.EpubHtml] = []
    for chapter in chapters:
        chapter_title = (chapter.translated_title or chapter.title or f"Chương {chapter.index}").strip()
        item = epub.EpubHtml(
            title=chapter_title,
            file_name=f"chapters/chapter_{chapter.index:04}.xhtml",
            lang="vi",
        )
        item.content = _chapter_body(
            chapter_title,
            chapter.translated_text or "",
            [chapter_title, chapter.translated_title or "", chapter.title or ""],
            chapter.index,
        )
        item.add_item(style)
        book.add_item(item)
        epub_chapters.append(item)

    book.toc = tuple(epub_chapters)
    book.spine = ["nav", *epub_chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    buffer = BytesIO()
    epub.write_epub(buffer, book, {})
    filename = f"{_slugify(title)}_{range_label}.vi.epub"
    return EpubExportResult(
        content=buffer.getvalue(),
        filename=filename,
        chapter_count=len(epub_chapters),
    )
