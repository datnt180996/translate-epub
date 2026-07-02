"""Tests for batch translate selection and eligibility rules."""
from __future__ import annotations

import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import app.main as main
from app.main import _batch_display_status, _chapter_detail_status, templates
from app.models import Chapter, Novel
from fastapi.responses import HTMLResponse


def _render_novel(novel, chapter_rows, batch_running: bool = False) -> str:
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
        fetch_running=False,
        pending_count=0,
        batch_translate_running=batch_running,
        poll_active=batch_running,
        eligible_translate_count=3,
        active_nav="home",
        flash=None,
    )


def _chapter(chapter_id: int, index: int, **kwargs) -> Chapter:
    return Chapter(
        id=chapter_id,
        novel_id=1,
        index=index,
        title=f"第{index}章",
        translated_title=f"Chương {index}",
        status=kwargs.get("status", "pending"),
        raw_text=kwargs.get("raw_text"),
        translated_text=kwargs.get("translated_text"),
    )


def test_novel_detail_renders_batch_form_and_checkboxes():
    rows = [
        {"chapter": _chapter(1, 1, status="fetched", raw_text="原文1"), "novel": Novel(id=1, title="t", source_type="web"), "display_status": "fetched"},
        {"chapter": _chapter(2, 2, status="fetched", raw_text="原文2", translated_text="Bản dịch 2"), "novel": Novel(id=1, title="t", source_type="web"), "display_status": "translated"},
        {"chapter": _chapter(3, 3), "novel": Novel(id=1, title="t", source_type="web"), "display_status": "not_fetched"},
    ]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    assert 'id="nd-batch-form"' in html
    assert 'action="/novels/1/translate-selected"' in html
    assert 'hx-post="/novels/1/translate-selected"' in html
    assert 'hx-target="#nd-chapter-tbody"' in html
    assert 'id="nd-batch-submit"' in html
    assert 'id="nd-select-all"' in html
    assert html.count('class="nd-batch-checkbox"') >= 3
    assert "data-chapter-id=\"1\"" in html
    assert "Dịch chương đã chọn" in html


def test_eligible_chapter_renders_active_checkbox():
    ch = _chapter(7, 7, status="fetched", raw_text="原文7")
    rows = [{
        "chapter": ch,
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": _chapter_detail_status(ch),
    }]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    assert 'data-batch-eligible="1"' in html
    assert 'data-chapter-id="7"' in html
    assert "Dịch chương đã chọn" in html


def test_translated_or_not_fetched_chapter_marks_not_eligible():
    ch_translated = _chapter(8, 8, status="translated", raw_text="原文", translated_text="Bản dịch")
    ch_not_fetched = _chapter(9, 9)
    rows = [
        {"chapter": ch_translated, "novel": Novel(id=1, title="t", source_type="web"), "display_status": _chapter_detail_status(ch_translated)},
        {"chapter": ch_not_fetched, "novel": Novel(id=1, title="t", source_type="web"), "display_status": _chapter_detail_status(ch_not_fetched)},
    ]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    assert 'data-chapter-id="8"' in html
    assert 'data-chapter-id="9"' in html
    assert 'data-batch-eligible="0"' in html
    assert html.count('data-batch-eligible="0"') >= 2


def test_batch_running_disables_form_and_swaps_label():
    rows = [{
        "chapter": _chapter(11, 1, status="fetched", raw_text="原文"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = templates.get_template("novel.html").render(
        novel=Novel(id=1, title="t", source_type="web"),
        chapters=[r["chapter"] for r in rows],
        chapter_rows=rows,
        glossary=[],
        style_guide="",
        novel_stats={"total": 1, "raw": 1, "translated": 0, "translating": 1, "fetching": 0, "error": 0, "not_fetched": 0, "active_error": 1},
        fetch_running=False,
        pending_count=0,
        batch_translate_running=True,
        poll_active=True,
        eligible_translate_count=1,
        active_nav="home",
        flash=None,
    )
    assert "Đang dịch hàng đợi" in html
    assert 'data-disabled="1"' in html


def test_batch_status_marks_current_translating_and_waiting_chapters_queue():
    current = {"id": 21, "status": "fetched", "has_raw": True, "has_translated": False}
    waiting = {"id": 22, "status": "fetched", "has_raw": True, "has_translated": False}
    done = {"id": 23, "status": "translated", "has_raw": True, "has_translated": True}
    batch_state = {
        "current_chapter_id": 21,
        "queued_chapter_ids": [22, 23],
    }

    assert _batch_display_status(current, batch_state) == "translating"
    assert _batch_display_status(waiting, batch_state) == "queue"
    assert _batch_display_status(done, batch_state) == "translated"

    html = templates.get_template("partials/novel_chapter_row.html").render(
        novel=Novel(id=1, title="t", source_type="web"),
        chapter=waiting,
        display_status="queue",
    )
    assert "Queue" in html
    assert 'data-batch-eligible="0"' in html


def test_batch_submit_preserves_page_and_table_scroll():
    rows = [{
        "chapter": _chapter(24, 24, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    assert "novel-batch-scroll:1" in html
    assert "windowY: window.scrollY" in html
    assert "tableY: tableWrap?.scrollTop" in html
    assert "window.scrollTo(0, savedScroll.windowY" in html


def test_batch_button_unlocks_when_polled_rows_have_no_active_translation():
    rows = [{
        "chapter": _chapter(25, 25, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = _render_novel(
        Novel(id=1, title="t", source_type="web"),
        rows,
        batch_running=True,
    )
    assert 'id="nd-batch-submit-label"' in html
    assert 'id="nd-batch-progress"' in html
    assert "refreshBatchRunning();" in html
    assert 'tr[data-display-status="queue"], tr[data-display-status="translating"]' in html
    assert "batchSubmitLabel.textContent = batchRunning" in html


def test_polling_continues_until_dom_is_clear():
    """Polling must keep going until the DOM shows no active row, even if the
    server reports poll-inactive. This guards against F5-required updates for
    single-chapter translation finishing on /novels."""
    rows = [{
        "chapter": _chapter(29, 29, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)

    assert "const recomputePollActive" in html
    assert "tbodyHasActiveRows" in html
    assert "ACTIVE_TBODY_SELECTOR" in html
    assert "domActive || serverActive" in html
    assert "recomputePollActive();" in html
    assert "htmx:swapError" in html
    assert "htmx:responseError" in html
    assert "htmx:sendError" in html
    assert "pollActive = activeHeader === '1'" not in html


def test_active_row_renders_self_poll_and_drops_when_translated():
    """Each active chapter row polls its own row endpoint every 2s so a
    single-chapter translation finishes without F5, even if the global table
    polling is stale or off."""
    novel = Novel(id=9, title="t", source_type="web")

    def render_row(display_status: str) -> str:
        return templates.get_template("partials/novel_chapter_row.html").render(
            novel=novel,
            chapter={"id": 91, "novel_id": 9, "index": 3, "title": "第3章", "translated_title": "Chương 3",
                     "source_url": None, "status": display_status, "has_raw": True, "has_translated": False},
            display_status=display_status,
        )

    active = render_row("translating")
    assert 'id="chapter-row-91"' in active
    assert 'hx-get="/novels/9/chapters/91/row"' in active
    assert 'hx-trigger="every 2s"' in active
    assert 'hx-target="this"' in active
    assert 'hx-swap="outerHTML"' in active
    assert 'hx-select="#chapter-row-91"' in active

    queue = render_row("queue")
    assert 'hx-get="/novels/9/chapters/91/row"' in queue

    fetching = render_row("fetching")
    assert 'hx-get="/novels/9/chapters/91/row"' in fetching

    translated = render_row("translated")
    assert 'hx-get="/novels/9/chapters/91/row"' not in translated
    assert 'hx-trigger="every 2s"' not in translated

    done = render_row("fetched")
    assert 'hx-get="/novels/9/chapters/91/row"' not in done


def test_chapter_row_carries_index_and_id_for_quick_select():
    """Quick-select UI relies on data-chapter-index / data-chapter-id on the
    row so JS can map selection to chapter numbers without parsing titles."""
    html = templates.get_template("partials/novel_chapter_row.html").render(
        novel=Novel(id=2, title="t", source_type="web"),
        chapter={"id": 42, "novel_id": 2, "index": 17, "title": "第17章", "translated_title": "Chương 17",
                 "source_url": None, "status": "fetched", "has_raw": True, "has_translated": False},
        display_status="fetched",
    )
    assert 'data-chapter-index="17"' in html
    assert 'data-chapter-id="42"' in html
    assert 'id="chapter-row-42"' in html


def test_novel_detail_renders_quick_select_controls():
    """The batch bar exposes range inputs, +10/+50 presets, visible and clear
    buttons so users can select many chapters without ticking each one."""
    rows = [{
        "chapter": _chapter(31, 5, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)

    assert 'class="nd-batch-quick"' in html
    assert 'id="nd-range-from"' in html
    assert 'id="nd-range-to"' in html
    assert 'id="nd-select-range"' in html
    assert "Chọn khoảng" in html
    assert 'id="nd-select-visible"' in html
    assert "Chọn đang lọc" in html
    assert 'data-select-next="10"' in html
    assert 'data-select-next="50"' in html
    assert 'id="nd-clear-selection"' in html
    assert "Bỏ chọn" in html
    assert "Shift" in html


def test_quick_select_controls_are_disabled_while_batch_running():
    rows = [{
        "chapter": _chapter(33, 1, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = templates.get_template("novel.html").render(
        novel=Novel(id=1, title="t", source_type="web"),
        chapters=[r["chapter"] for r in rows],
        chapter_rows=rows,
        glossary=[],
        style_guide="",
        novel_stats={"total": 1, "raw": 1, "translated": 0, "translating": 1, "fetching": 0, "error": 0, "not_fetched": 0, "active_error": 1},
        fetch_running=False,
        pending_count=0,
        batch_translate_running=True,
        poll_active=True,
        eligible_translate_count=1,
        active_nav="home",
        flash=None,
    )
    assert 'id="nd-select-range" type="button" class="nd-btn nd-btn-ghost" disabled' in html
    assert 'data-select-next="10"' in html and 'data-select-next="10" disabled' in html
    assert 'data-select-next="50" disabled' in html
    assert 'id="nd-clear-selection" type="button" class="nd-btn nd-btn-ghost" disabled' in html
    assert 'id="nd-select-visible" type="button" class="nd-btn nd-btn-ghost" disabled' in html
    assert '<input id="nd-range-from" type="number"' in html and 'id="nd-range-from" type="number" min="1" inputmode="numeric" placeholder="7" disabled>' in html
    assert '<input id="nd-range-to" type="number"' in html and 'id="nd-range-to" type="number" min="1" inputmode="numeric" placeholder="30" disabled>' in html


def test_quick_select_js_functions_exist():
    rows = [{
        "chapter": _chapter(34, 1, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    for symbol in (
        "selectRangeByIndex",
        "selectNextEligible",
        "visibleEligibleRows",
        "clearSelection",
        "lastClickedCheckbox",
        "setSelectionForRows",
        "collectQuickControls",
    ):
        assert symbol in html, f"missing JS symbol: {symbol}"


def test_htmx_batch_submit_returns_rows_without_redirect():
    class Request:
        headers = {"HX-Request": "true"}
        session = {}

    class Session:
        def get(self, model, item_id):
            return Novel(id=item_id, title="t", source_type="web")

    originals = (
        main.default_provider,
        main.is_batch_translating_novel,
        main.filter_eligible_for_novel,
        main.start_batch_translation,
        main.novel_chapters_partial,
    )
    try:
        main.default_provider = lambda session: "minimax"
        main.is_batch_translating_novel = lambda novel_id: False
        main.filter_eligible_for_novel = lambda novel_id, chapter_ids: list(chapter_ids)
        main.start_batch_translation = lambda novel_id, chapter_ids, provider: (True, len(chapter_ids))
        main.novel_chapters_partial = lambda request, novel_id, session: HTMLResponse(
            "<tr><td>Queue</td></tr>",
            headers={"X-Novel-Poll-Active": "1"},
        )

        response = asyncio.run(
            main.translate_selected(1, Request(), chapter_ids=[10, 11], session=Session())
        )
        assert response.status_code == 200
        assert response.headers.get("location") is None
        assert response.headers["x-novel-poll-active"] == "1"
        assert b"Queue" in response.body
    finally:
        (
            main.default_provider,
            main.is_batch_translating_novel,
            main.filter_eligible_for_novel,
            main.start_batch_translation,
            main.novel_chapters_partial,
        ) = originals


def test_htmx_batch_validation_error_does_not_redirect():
    class Request:
        headers = {"HX-Request": "true"}
        session = {}

    class Session:
        def get(self, model, item_id):
            return Novel(id=item_id, title="t", source_type="web")

    original_default = main.default_provider
    try:
        main.default_provider = lambda session: None
        response = asyncio.run(
            main.translate_selected(1, Request(), chapter_ids=[10], session=Session())
        )
        assert response.status_code == 204
        assert response.headers.get("location") is None
        assert "novel-batch-notice" in response.headers["hx-trigger"]
    finally:
        main.default_provider = original_default


def test_full_page_htmx_response_is_never_swapped_into_chapter_table():
    rows = [{
        "chapter": _chapter(26, 26, status="fetched", raw_text="raw"),
        "novel": Novel(id=1, title="t", source_type="web"),
        "display_status": "fetched",
    }]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    assert 'responseText.includes(\'<body class="novel-detail-page"\')' in html
    assert "event.detail.shouldSwap = false" in html
    assert "htmx.trigger(document.body, 'novel-chapters-refresh')" in html
    assert "recomputePollActive()" in html


def test_batch_submit_updates_selected_rows_optimistically():
    rows = [
        {
            "chapter": _chapter(27, 27, status="fetched", raw_text="raw"),
            "novel": Novel(id=1, title="t", source_type="web"),
            "display_status": "fetched",
        },
        {
            "chapter": _chapter(28, 28, status="fetched", raw_text="raw"),
            "novel": Novel(id=1, title="t", source_type="web"),
            "display_status": "fetched",
        },
    ]
    html = _render_novel(Novel(id=1, title="t", source_type="web"), rows)
    assert "const showOptimisticBatchStatuses" in html
    assert "const status = index === 0 ? 'translating' : 'queue'" in html
    assert "showOptimisticBatchStatuses();" in html
    assert "nd-pill-translating" in html
    assert "nd-pill-queue" in html


if __name__ == "__main__":
    test_novel_detail_renders_batch_form_and_checkboxes()
    print("PASS test_novel_detail_renders_batch_form_and_checkboxes")
    test_eligible_chapter_renders_active_checkbox()
    print("PASS test_eligible_chapter_renders_active_checkbox")
    test_translated_or_not_fetched_chapter_marks_not_eligible()
    print("PASS test_translated_or_not_fetched_chapter_marks_not_eligible")
    test_batch_running_disables_form_and_swaps_label()
    print("PASS test_batch_running_disables_form_and_swaps_label")
    print("\nAll 4 batch translate UI tests passed.")
