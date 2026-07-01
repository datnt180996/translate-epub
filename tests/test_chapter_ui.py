"""Regression tests for the chapter reader context and template."""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import _chapter_detail_status, chapter_view, templates
from app.models import Chapter, Novel


def _chapter(
    chapter_id: int,
    index: int,
    *,
    status: str = "pending",
    raw_text: str | None = None,
    translated_text: str | None = None,
) -> Chapter:
    return Chapter(
        id=chapter_id,
        novel_id=1,
        index=index,
        title=f"第{index}章",
        translated_title=f"Chương {index}",
        status=status,
        raw_text=raw_text,
        translated_text=translated_text,
    )


def _render(chapter: Chapter, chapters: list[Chapter], view: str = "vi") -> str:
    return templates.get_template("chapter.html").render(
        novel=Novel(id=1, title="Đại Đạo Triều Thiên", source_type="web"),
        chapter=chapter,
        prev_id=None,
        next_id=chapters[1].id if len(chapters) > 1 else None,
        view=view,
        display_status=_chapter_detail_status(chapter),
        chapter_items=[
            {"chapter": item, "display_status": _chapter_detail_status(item)}
            for item in chapters
        ],
        providers=["minimax"],
        default_provider="minimax",
        has_provider=True,
        job=None,
        active_nav="home",
        flash=None,
    )


def test_chapter_status_prefers_content_and_active_states():
    assert _chapter_detail_status(_chapter(1, 1, translated_text="Đã dịch")) == "translated"
    assert _chapter_detail_status(_chapter(2, 2, status="translating", raw_text="原文")) == "translating"
    assert _chapter_detail_status(_chapter(3, 3, status="fetching")) == "fetching"
    assert _chapter_detail_status(_chapter(4, 4, status="error")) == "error"
    assert _chapter_detail_status(_chapter(5, 5, raw_text="原文")) == "fetched"
    assert _chapter_detail_status(_chapter(6, 6)) == "not_fetched"


def test_reader_renders_parallel_content_and_searchable_modal():
    current = _chapter(1, 1, raw_text="朝天大陆。", translated_text="Triều Thiên đại lục.")
    translating = _chapter(2, 2, status="translating", raw_text="原文")
    html = _render(current, [current, translating], view="both")

    assert 'class="chapter-reader-page"' in html
    assert 'class="cr-reading-card cr-reading-pair"' in html
    assert "朝天大陆。" in html
    assert "Triều Thiên đại lục." in html
    assert 'id="chapterListDialog"' in html
    assert 'data-search="2 chuong 2 chương 2 chapter 2 Chương 2 第2章"' in html
    assert "Đang dịch" in html
    assert 'class="cr-dialog-item active"' in html
    assert "Gốc:" not in html
    assert "Provider:" not in html
    assert '<button type="submit" class="cr-action-button"' not in html
    assert html.index('class="cr-tabs"') < html.index('class="cr-chapter-nav"') < html.index('class="cr-reading-card')


def test_untranslated_chapter_keeps_translate_action():
    chapter = _chapter(1, 1, raw_text="原文")
    html = _render(chapter, [chapter])
    assert 'name="return_to" value="/chapters/1"' in html
    assert "DỊCH" in html


def test_modal_can_lazy_load_when_route_context_is_stale():
    chapter = _chapter(1, 1, raw_text="原文")
    html = templates.get_template("chapter.html").render(
        novel=Novel(id=1, title="Đại Đạo Triều Thiên", source_type="web"),
        chapter=chapter,
        prev_id=None,
        next_id=None,
        view="vi",
        default_provider="minimax",
        job=None,
        flash=None,
    )
    assert "Đang tải danh sách chương..." in html
    assert "fetch('/novels/1/chapters')" in html


def test_reader_keeps_vietnamese_as_default_view():
    parameter = inspect.signature(chapter_view).parameters["view"]
    assert parameter.default == "vi"

    chapter = _chapter(1, 1, raw_text="原文", translated_text="Bản dịch")
    html = _render(chapter, [chapter])
    assert 'href="/chapters/1?view=vi" class="active"' in html
    assert "Bản dịch" in html
    assert "原文" not in html


if __name__ == "__main__":
    tests = [
        test_chapter_status_prefers_content_and_active_states,
        test_reader_renders_parallel_content_and_searchable_modal,
        test_untranslated_chapter_keeps_translate_action,
        test_modal_can_lazy_load_when_route_context_is_stale,
        test_reader_keeps_vietnamese_as_default_view,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
