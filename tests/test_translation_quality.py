"""Tests for the translation quality gate and retry paths."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import templates
from app.models import Chapter, Novel
from app.services.glossary_service import _raise_if_severe_line_mismatch, translation_quality_status
from app.services.providers import minimax as provider_mod


def test_quality_status_clean_vietnamese():
    text = "Đây là bản dịch tiếng Việt sạch, không có chữ Hán."
    assert translation_quality_status(text, "原文") == "ok"


def test_quality_status_missing_translation():
    assert translation_quality_status(None, "原文") == "missing"
    assert translation_quality_status("   ", "原文") == "missing"


def test_quality_status_identical_to_raw_is_bad():
    raw = "原文内容"
    assert translation_quality_status(raw, raw) == "bad"


def test_quality_status_heavy_cjk_is_bad():
    raw = "这是一段中文原文内容，包含多行句子。"
    bad = (
        "这是一段中文原文内容，包含多行句子。"
        "这是另一段内容。这是第三段内容。这一段仍然包含中文。"
        "多余内容 chính là tiếng Việt."
    )
    quality = translation_quality_status(bad, raw)
    assert quality == "bad"


def test_quality_status_a_few_cjk_is_warning():
    text = "Bản dịch có lẫn vài từ Hán như 师傅 ở đây thôi."
    quality = translation_quality_status(text, "原文")
    assert quality == "warning"


def test_row_partial_shows_bad_quality_pill():
    novel = Novel(id=1, title="t", source_type="web")
    chapter_row = {
        "id": 7,
        "novel_id": 1,
        "index": 7,
        "title": "第7章",
        "translated_title": "Chương 7",
        "source_url": None,
        "status": "translated",
        "has_raw": True,
        "has_translated": True,
        "quality": "bad",
    }
    html = templates.get_template("partials/novel_chapter_row.html").render(
        novel=novel,
        chapter=chapter_row,
        display_status="translated",
    )
    assert "Lỗi dịch" in html
    assert 'data-quality="bad"' in html
    assert 'action="/chapters/7/translate"' not in html


def test_row_partial_no_action_cells_for_good_quality():
    novel = Novel(id=1, title="t", source_type="web")
    chapter_row = {
        "id": 9,
        "novel_id": 1,
        "index": 9,
        "title": "第9章",
        "translated_title": "Chương 9",
        "source_url": None,
        "status": "translated",
        "has_raw": True,
        "has_translated": True,
        "quality": "ok",
    }
    html = templates.get_template("partials/novel_chapter_row.html").render(
        novel=novel,
        chapter=chapter_row,
        display_status="translated",
    )
    assert "Lỗi dịch" not in html
    assert 'class="nd-action-cell"' not in html
    assert 'href="/chapters/9"' in html


def test_chapter_detail_shows_bad_quality_alert_and_retry():
    novel = Novel(id=1, title="t", source_type="web")
    chapter = Chapter(
        id=10,
        novel_id=1,
        index=10,
        title="第10章",
        translated_title="Chương 10",
        status="translated",
        raw_text="原文",
        translated_text="原文",
    )
    html = templates.get_template("chapter.html").render(
        novel=novel,
        chapter=chapter,
        prev_id=None,
        next_id=None,
        view="vi",
        display_status="translated",
        translation_quality="bad",
        chapter_items=[],
        chapter_quality_by_id={},
        providers=["minimax"],
        default_provider="minimax",
        has_provider=True,
        job=None,
        active_nav="home",
        flash=None,
    )
    assert "Bản dịch lỗi" in html
    assert "Dịch lại" in html or "DỊCH LẠI" in html
    assert 'action="/chapters/10/translate"' in html


def test_chapter_detail_no_retry_for_ok_quality():
    novel = Novel(id=1, title="t", source_type="web")
    chapter = Chapter(
        id=11,
        novel_id=1,
        index=11,
        title="第11章",
        translated_title="Chương 11",
        status="translated",
        raw_text="原文",
        translated_text="Bản dịch sạch không còn chữ Hán.",
    )
    html = templates.get_template("chapter.html").render(
        novel=novel,
        chapter=chapter,
        prev_id=None,
        next_id=None,
        view="vi",
        display_status="translated",
        translation_quality="ok",
        chapter_items=[],
        chapter_quality_by_id={},
        providers=["minimax"],
        default_provider="minimax",
        has_provider=True,
        job=None,
        active_nav="home",
        flash=None,
    )
    assert "DỊCH LẠI" not in html
    assert "Bản dịch lỗi" not in html


def test_severe_line_mismatch_raises():
    source = "\n".join(f"dòng gốc {i}" for i in range(30))
    translated = "Bản dịch bị cắt."
    try:
        _raise_if_severe_line_mismatch(source, translated, "test")
    except RuntimeError as exc:
        assert "thiếu/lệch dòng nghiêm trọng" in str(exc)
    else:
        raise AssertionError("Expected severe line mismatch to raise")


def test_provider_rejects_length_finish_reason():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {"content": "Tóc dài và"},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"completion_tokens": 8192},
            }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            assert json["max_tokens"] > 0
            return FakeResponse()

    original_client = provider_mod.httpx.Client
    provider_mod.httpx.Client = FakeClient
    try:
        provider = provider_mod.OpenAICompatProvider(
            name="openrouter",
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            model="google/gemini-2.5-flash-lite",
        )
        try:
            provider._chat("system", "user", temperature=0.0)
        except RuntimeError as exc:
            assert "finish_reason=length" in str(exc)
        else:
            raise AssertionError("Expected finish_reason=length to raise")
    finally:
        provider_mod.httpx.Client = original_client


def test_provider_retries_finish_reason_error_once():
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        calls = 0

        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            FakeClient.calls += 1
            if FakeClient.calls == 1:
                return FakeResponse(
                    {
                        "choices": [{"message": {"content": ""}, "finish_reason": "error"}],
                        "error": {"message": "upstream error"},
                        "usage": {"completion_tokens": 0},
                    }
                )
            return FakeResponse(
                {
                    "choices": [{"message": {"content": "Bản dịch đầy đủ."}, "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 4},
                }
            )

    original_client = provider_mod.httpx.Client
    provider_mod.httpx.Client = FakeClient
    try:
        provider = provider_mod.OpenAICompatProvider(
            name="openrouter",
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            model="google/gemini-2.5-flash-lite",
        )
        assert provider._chat("system", "user", temperature=0.0) == "Bản dịch đầy đủ."
        assert FakeClient.calls == 2
    finally:
        provider_mod.httpx.Client = original_client


if __name__ == "__main__":
    test_quality_status_clean_vietnamese()
    print("PASS test_quality_status_clean_vietnamese")
    test_quality_status_missing_translation()
    print("PASS test_quality_status_missing_translation")
    test_quality_status_identical_to_raw_is_bad()
    print("PASS test_quality_status_identical_to_raw_is_bad")
    test_quality_status_heavy_cjk_is_bad()
    print("PASS test_quality_status_heavy_cjk_is_bad")
    test_quality_status_a_few_cjk_is_warning()
    print("PASS test_quality_status_a_few_cjk_is_warning")
    test_row_partial_shows_bad_quality_pill()
    print("PASS test_row_partial_shows_bad_quality_pill")
    test_row_partial_no_action_cells_for_good_quality()
    print("PASS test_row_partial_no_action_cells_for_good_quality")
    test_chapter_detail_shows_bad_quality_alert_and_retry()
    print("PASS test_chapter_detail_shows_bad_quality_alert_and_retry")
    test_chapter_detail_no_retry_for_ok_quality()
    print("PASS test_chapter_detail_no_retry_for_ok_quality")
    test_severe_line_mismatch_raises()
    print("PASS test_severe_line_mismatch_raises")
    test_provider_rejects_length_finish_reason()
    print("PASS test_provider_rejects_length_finish_reason")
    test_provider_retries_finish_reason_error_once()
    print("PASS test_provider_retries_finish_reason_error_once")
    print("\nAll 12 translation quality tests passed.")
