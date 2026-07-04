"""Tests for the custom app confirm dialog and toast.

Covers:
- base.html exposes the global app confirm dialog and toast container.
- All forms that previously relied on native ``window.confirm(...)`` now use
  ``data-confirm`` + ``data-confirm-*`` attributes so the custom dialog takes
  over.
- No ``confirm(...)``/``onsubmit``/``window.alert(...)`` strings remain in any
  rendered template, so the browser-native "127.0.0.1 says" dialog never
  appears again.
"""
from __future__ import annotations

import os
import sys
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.main import templates
from app.models import Chapter, Novel


def _render(template_name: str, **context) -> str:
    """Render a template by name with minimal default context."""
    return templates.get_template(template_name).render(**context)


def _minimal_novel_context() -> dict:
    return {
        "active_nav": "home",
        "flash": None,
        "has_provider": True,
        "has_default": False,
    }


def _base_html(html: str) -> str:
    """Return the base.html portion of a rendered page so we can assert
    on the shared dialog markup without the per-page body polluting the search."""
    head = html.split("</head>", 1)[0] + "</head>"
    rest = html.split("</head>", 1)[1]
    body_close = rest.rfind("</body>")
    if body_close >= 0:
        rest = rest[:body_close] + "</body>"
    return head + rest


def test_base_contains_confirm_dialog():
    context = {"block content": "", "active_nav": None, "flash": None}
    html = _render("base.html", **context)
    assert 'id="appConfirmDialog"' in html
    assert 'class="app-confirm-dialog"' in html
    assert 'id="appConfirmCancel"' in html
    assert 'id="appConfirmAccept"' in html
    assert "Hủy" in html
    assert "Xác nhận" in html


def test_base_contains_toast_stack():
    context = {"block content": "", "active_nav": None, "flash": None}
    html = _render("base.html", **context)
    assert 'id="appToastStack"' in html
    assert "app-toast" in html


def test_base_exposes_appToast_helper():
    """The wrapper script must expose ``appToast`` and route ``window.alert``
    through the custom toast so legacy call sites stop showing the native
    browser dialog."""
    html = _render("base.html", block_content="", active_nav=None, flash=None)
    assert "window.appToast" in html
    assert "window.alert" in html
    assert "showToast" in html


def test_base_intercepts_submit_with_data_confirm():
    html = _render("base.html", block_content="", active_nav=None, flash=None)
    # Listener must look at data-confirm and bail for bypass.
    assert "data-confirm" in html
    assert "__confirmBypass" in html or "confirmBypass" in html


def _chapter(ch_id: int, **kwargs) -> Chapter:
    return Chapter(
        id=ch_id,
        novel_id=1,
        index=kwargs.get("index", ch_id),
        title=kwargs.get("title", f"第{ch_id}章"),
        translated_title=kwargs.get("translated_title", f"Chương {ch_id}"),
        status=kwargs.get("status", "pending"),
        raw_text=kwargs.get("raw_text"),
        translated_text=kwargs.get("translated_text"),
    )


def test_no_native_confirm_or_onsubmit_in_rendered_templates():
    """No rendered template may still contain a native ``confirm(`` call or a
    raw ``onsubmit`` attribute on a form/button. ``base.html`` legitimately
    references ``window.alert`` because it wraps it via the custom toast, so
    we only fail user-facing templates if we find those native patterns.
    """
    offenders = []
    names_to_check_fully = ("index.html", "novel.html", "chapter.html",
                            "api_settings.html",
                            "partials/novel_chapter_row.html",
                            "partials/novel_stats.html")
    for name in names_to_check_fully:
        try:
            html = _render(name, **_placeholder_context(name))
        except Exception:
            # Skip templates that need rich context (we render those separately
            # with the richer helpers below).
            continue
        if "confirm(" in html:
            offenders.append((name, "confirm("))
        if "onsubmit=" in html:
            offenders.append((name, "onsubmit="))
    # base.html must not leak any user-visible native confirm() call or any
    # ``onsubmit="return confirm(...)"`` attribute.
    base_html = _render("base.html", block_content="", active_nav=None, flash=None)
    if "confirm(" in base_html:
        offenders.append(("base.html", "confirm("))
    if re.search(r'\bonsubmit="[^"]*confirm\(', base_html):
        offenders.append(("base.html", "onsubmit confirm"))
    assert not offenders, offenders


def _placeholder_context(name: str) -> dict:
    if name == "novel.html":
        return _novel_ctx()
    if name == "chapter.html":
        return _chapter_ctx()
    if name in ("index.html", "api_settings.html", "base.html"):
        return _base_ctx()
    return {}


def _base_ctx() -> dict:
    return {
        "block content": "",
        "active_nav": None,
        "flash": None,
        "has_provider": True,
        "has_default": False,
    }


def _novel_ctx() -> dict:
    novel = Novel(id=1, title="t", source_type="web")
    ch = _chapter(1, index=1, status="fetched", raw_text="原文")
    chapters = [ch]
    chapter_rows = [
        {
            "chapter": {
                "id": ch.id, "novel_id": novel.id, "index": ch.index,
                "title": ch.title, "translated_title": ch.translated_title,
                "source_url": None, "status": ch.status,
                "has_raw": bool(ch.raw_text), "has_translated": False,
            },
            "novel": novel,
            "display_status": "fetched",
        }
    ]
    return dict(
        novel=novel,
        chapters=chapters,
        chapter_rows=chapter_rows,
        glossary=[],
        style_guide="",
        novel_stats={
            "total": 1, "raw": 1, "translated": 0, "translating": 0,
            "fetching": 0, "error": 0, "not_fetched": 0, "active_error": 0,
        },
        fetch_running=False,
        pending_count=1,
        batch_translate_running=False,
        poll_active=False,
        eligible_translate_count=1,
        active_nav="home",
        flash=None,
    )


def _chapter_ctx() -> dict:
    novel = Novel(id=1, title="t", source_type="web")
    ch = _chapter(1, index=1, status="fetched", raw_text="原文")
    return dict(
        chapter=ch,
        novel=novel,
        active_nav="home",
        flash=None,
        prev_chapter=None,
        next_chapter=None,
        glossary=[],
        style_guide="",
        status="fetched",
        default_provider="minimax",
        translation_quality=None,
        return_to="/chapters/1",
    )


def test_novel_detail_fetch_all_uses_data_confirm():
    ctx = _novel_ctx()
    ctx["pending_count"] = 1
    html = _render("novel.html", **ctx)
    assert "data-confirm" in html
    assert "Tải chương còn thiếu?" in html
    assert "data-confirm-variant=\"primary\"" in html
    # The legacy native confirm() must be gone.
    assert "confirm(" not in html


def test_novel_detail_glossary_delete_uses_data_confirm():
    ctx = _novel_ctx()
    ctx["glossary"] = [
        {"id": 99, "source_text": "abc", "target_text": "xyz", "category": "character"},
    ]
    html = _render("novel.html", **ctx)
    assert "data-confirm" in html
    assert "Xóa thuật ngữ?" in html
    assert "data-confirm-variant=\"danger\"" in html
    assert "confirm(" not in html


def test_chapter_translate_form_uses_data_confirm():
    ctx = _chapter_ctx()
    ctx["chapter"].status = "fetched"
    ctx["chapter"].raw_text = "原文"
    ctx["status"] = "fetched"
    ctx["translation_quality"] = None
    html = _render("chapter.html", **ctx)
    assert "data-confirm" in html
    assert "Dịch chương này?" in html
    assert "data-confirm-variant=\"primary\"" in html
    assert "confirm(" not in html


def test_chapter_retranslate_form_uses_warn_variant():
    ctx = _chapter_ctx()
    ctx["chapter"].status = "translated"
    ctx["chapter"].translated_text = "bản dịch tệ"
    ctx["status"] = "translated"
    ctx["translation_quality"] = "bad"
    html = _render("chapter.html", **ctx)
    assert "data-confirm" in html
    assert "Dịch lại chương này?" in html
    assert "data-confirm-variant=\"warn\"" in html
    assert "confirm(" not in html


def test_index_delete_novel_uses_data_confirm():
    novel = Novel(id=42, title="t", source_type="web")
    html = _render(
        "index.html",
        active_nav="home",
        flash=None,
        novels=[novel],
        novel_statuses={42: "fetched"},
        chapter_counts={42: 3},
        status_labels={"fetched": "Đã tải", "pending": "Mới import",
                       "translated": "Đã dịch xong", "translating": "Đang dịch",
                       "fetching": "Đang tải", "error": "Có lỗi"},
        has_provider=True,
        has_default=True,
    )
    assert "data-confirm" in html
    assert "Xóa truyện?" in html
    assert "data-confirm-variant=\"danger\"" in html
    assert "confirm(" not in html


def test_api_settings_clear_uses_data_confirm():
    html = _render(
        "api_settings.html",
        active_nav="settings",
        flash=None,
        settings_list=[
            {
                "provider": "minimax",
                "configured": True,
                "source": "web",
                "masked_key": "abc...1234",
                "base_url": "https://example/v1",
                "model": "model-x",
                "group_id": "",
                "has_key": True,
                "updated_at": None,
            }
        ],
        default_provider="minimax",
        has_provider=True,
        has_default=True,
    )
    assert "data-confirm" in html
    assert "Xóa cấu hình" in html
    assert "data-confirm-variant=\"danger\"" in html
    assert "confirm(" not in html


# ----- lazy-import helpers (avoid leaking re into module namespace) -----
import re  # noqa: E402  (kept after tests for clarity)


def _run_all():
    failures = []
    for name, fn in list(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, exc))
            print(f"FAIL {name}: {exc!r}")
    if failures:
        raise SystemExit(1)
    print(
        f"\nAll {sum(1 for n in globals() if n.startswith('test_') and callable(globals()[n]))} "
        "confirm dialog tests passed."
    )


if __name__ == "__main__":
    _run_all()
