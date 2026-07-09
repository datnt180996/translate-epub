"""Regression tests for novel detail performance optimizations (phase 1).

Covers:
- Lightweight chapter row helper produces display_status matching full Chapter.
- Stats helpers (row-based and SQL aggregate) match the legacy Python stats.
- Novel detail and chapters partial render lightweight rows.
- Polling trigger is conditional on fetch/batch job running.
- Homepage does not load chapter text.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.main import (
    _chapter_detail_status,
    _display_status_from_row,
    _query_chapter_neighbors,
    _query_homepage_chapter_meta,
    _novel_stats_aggregate,
    _novel_stats_from_rows,
    _novel_poll_active,
    templates,
)
from app.models import Chapter, Novel


def _chapter(cid: int, index: int, **kwargs) -> Chapter:
    return Chapter(
        id=cid,
        novel_id=1,
        index=index,
        title=f"第{index}章",
        translated_title=f"Chương {index}",
        status=kwargs.get("status", "pending"),
        raw_text=kwargs.get("raw_text"),
        translated_text=kwargs.get("translated_text"),
    )


def _row_from_chapter(chapter: Chapter) -> dict:
    return {
        "id": chapter.id,
        "novel_id": chapter.novel_id,
        "index": chapter.index,
        "title": chapter.title,
        "translated_title": chapter.translated_title,
        "source_url": getattr(chapter, "source_url", None),
        "status": chapter.status or "",
        "has_raw": bool(chapter.raw_text),
        "has_translated": bool(chapter.translated_text),
    }


def test_display_status_from_row_matches_chapter_helper():
    cases = [
        _chapter(1, 1, translated_text="Đã dịch"),
        _chapter(2, 2, status="translating", raw_text="原文"),
        _chapter(3, 3, status="fetching"),
        _chapter(4, 4, status="error"),
        _chapter(5, 5, raw_text="原文"),
        _chapter(6, 6),
    ]
    for ch in cases:
        row = _row_from_chapter(ch)
        assert _display_status_from_row(row) == _chapter_detail_status(ch), ch


def test_novel_stats_from_rows_matches_legacy_counts():
    chapters = [
        _chapter(1, 1, translated_text="vi"),
        _chapter(2, 2, status="translating", raw_text="raw"),
        _chapter(3, 3, status="fetching"),
        _chapter(4, 4, status="error"),
        _chapter(5, 5, raw_text="raw"),
        _chapter(6, 6),
    ]
    rows = [_row_from_chapter(c) for c in chapters]
    from app.main import _novel_stats_from_chapters
    legacy = _novel_stats_from_chapters(chapters)
    new = _novel_stats_from_rows(rows)
    assert new == legacy


def test_novel_stats_aggregate_matches_legacy_counts():
    """Aggregate stats computed via SQL must match the row-based stats helper."""
    from app.models import Novel
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    chapters = [
        _chapter(1, 1, translated_text="vi"),
        _chapter(2, 2, status="translating", raw_text="raw"),
        _chapter(3, 3, status="fetching"),
        _chapter(4, 4, status="error"),
        _chapter(5, 5, raw_text="raw"),
        _chapter(6, 6),
    ]
    rows = [_row_from_chapter(c) for c in chapters]
    expected = _novel_stats_from_rows(rows)
    with Session(engine) as session:
        novel = Novel(id=1, title="t", source_type="web")
        session.add(novel)
        for c in chapters:
            c.novel_id = novel.id
            session.add(c)
        session.commit()
        agg = _novel_stats_aggregate(session, novel.id)
    assert agg == expected


def test_homepage_chapter_meta_matches_per_novel_status_counts():
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        n1 = Novel(id=1, title="one", source_type="web")
        n2 = Novel(id=2, title="two", source_type="web")
        n3 = Novel(id=3, title="empty", source_type="web")
        session.add_all([n1, n2, n3])
        session.add_all(
            [
                Chapter(novel_id=1, index=1, title="c1", status="translated"),
                Chapter(novel_id=1, index=2, title="c2", status="translated"),
                Chapter(novel_id=2, index=1, title="c1", status="fetched"),
                Chapter(novel_id=2, index=2, title="c2", status="error"),
            ]
        )
        session.commit()

        counts, statuses = _query_homepage_chapter_meta(session, [1, 2, 3])

    assert counts == {1: 2, 2: 2, 3: 0}
    assert statuses == {1: "translated", 2: "error", 3: "pending"}


def test_chapter_neighbors_use_index_order():
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        novel = Novel(id=1, title="t", source_type="web")
        session.add(novel)
        session.add_all(
            [
                Chapter(id=10, novel_id=1, index=10, title="c10", raw_text="heavy text"),
                Chapter(id=20, novel_id=1, index=20, title="c20", raw_text="heavy text"),
                Chapter(id=30, novel_id=1, index=30, title="c30", raw_text="heavy text"),
            ]
        )
        session.commit()
        current = session.get(Chapter, 20)
        prev_id, next_id = _query_chapter_neighbors(session, current)

    assert prev_id == 10
    assert next_id == 30


def _render_novel_html(chapter_rows, *, fetch_running=False, batch_running=False, novel=None):
    novel = novel or Novel(id=1, title="t", source_type="web")
    chapters = [row["chapter"] for row in chapter_rows]
    stats = {
        "total": len(chapters),
        "raw": 0,
        "translated": 0,
        "translating": 0,
        "fetching": 0,
        "error": 0,
        "not_fetched": 0,
        "active_error": 0,
    }
    return templates.get_template("novel.html").render(
        novel=novel,
        chapters=chapters,
        chapter_rows=chapter_rows,
        glossary=[],
        style_guide="",
        novel_stats=stats,
        fetch_running=fetch_running,
        pending_count=0,
        batch_translate_running=batch_running,
        poll_active=fetch_running or batch_running,
        eligible_translate_count=0,
        active_nav="home",
        flash=None,
    )


def test_lightweight_row_template_renders_eligible_checkbox():
    ch = _chapter(7, 7, status="fetched", raw_text="原文")
    row_dict = _row_from_chapter(ch)
    rows = [{
        "chapter": row_dict,
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": _display_status_from_row(row_dict),
    }]
    html = _render_novel_html(rows)
    assert 'data-batch-eligible="1"' in html
    assert 'data-chapter-id="7"' in html


def _tbody_trigger(html: str) -> str:
    import re
    m = re.search(r'<tbody[^>]*hx-trigger="([^"]*)"', html)
    assert m, "tbody trigger not found"
    return m.group(1)


def test_table_uses_event_trigger_without_declarative_polling():
    ch = _chapter(1, 1, status="fetched", raw_text="x")
    row = _row_from_chapter(ch)
    rows = [{"chapter": row, "novel": Novel(id=1, title="t", source_type="web"), "display_status": "fetched"}]

    for fetch_running, batch_running in ((False, False), (True, False), (False, True)):
        html = _render_novel_html(
            rows,
            fetch_running=fetch_running,
            batch_running=batch_running,
        )
        trigger = _tbody_trigger(html)
        assert trigger == "novel-chapters-refresh from:body"
        expected_state = "1" if fetch_running or batch_running else "0"
        assert f'data-poll-active="{expected_state}"' in html


def test_poll_active_only_for_running_work():
    idle = {"translating": 0, "fetching": 0}
    assert _novel_poll_active(idle) is False
    assert _novel_poll_active(idle, fetch_running=True) is True
    assert _novel_poll_active(idle, batch_state={"chapter_ids": [1]}) is True
    assert _novel_poll_active({"translating": 1, "fetching": 0}) is True
    assert _novel_poll_active({"translating": 0, "fetching": 1}) is True


def test_stats_partial_has_no_self_polling():
    html = templates.get_template("partials/novel_stats.html").render(
        novel=Novel(id=1, title="t", source_type="web"),
        stats={"total": 1, "raw": 0, "translated": 0, "active_error": 0},
    )
    assert "every 5s" not in html
    assert "hx-get" not in html


def test_no_load_trigger_on_initial_table_render():
    ch = _chapter(1, 1, status="fetched", raw_text="x")
    row = _row_from_chapter(ch)
    rows = [{"chapter": row, "novel": Novel(id=1, title="t", source_type="web"), "display_status": "fetched"}]
    html = _render_novel_html(rows)
    trigger = _tbody_trigger(html)
    assert "load" not in trigger


if __name__ == "__main__":
    test_display_status_from_row_matches_chapter_helper()
    print("PASS test_display_status_from_row_matches_chapter_helper")
    test_novel_stats_from_rows_matches_legacy_counts()
    print("PASS test_novel_stats_from_rows_matches_legacy_counts")
    test_novel_stats_aggregate_matches_legacy_counts()
    print("PASS test_novel_stats_aggregate_matches_legacy_counts")
    test_homepage_chapter_meta_matches_per_novel_status_counts()
    print("PASS test_homepage_chapter_meta_matches_per_novel_status_counts")
    test_chapter_neighbors_use_index_order()
    print("PASS test_chapter_neighbors_use_index_order")
    test_lightweight_row_template_renders_eligible_checkbox()
    print("PASS test_lightweight_row_template_renders_eligible_checkbox")
    test_table_uses_event_trigger_without_declarative_polling()
    print("PASS test_table_uses_event_trigger_without_declarative_polling")
    test_no_load_trigger_on_initial_table_render()
    print("PASS test_no_load_trigger_on_initial_table_render")
    print("\nAll 6 novel detail performance tests passed.")
