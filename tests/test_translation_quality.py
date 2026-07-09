"""Tests for the translation quality gate and retry paths."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, SQLModel, create_engine

from app.config import Settings
from app.main import templates
from app.models import Chapter, Novel
from app.services import glossary_service as glossary_mod
from app.services.glossary_service import (
    _raise_if_severe_line_mismatch,
    _repair_line_alignment,
    translate_chapter,
    translation_quality_status,
)
from app.services.providers import minimax as provider_mod


def test_quality_status_clean_vietnamese():
    text = "Đây là bản dịch tiếng Việt sạch, không có chữ Hán."
    assert translation_quality_status(text, "\u539f\u6587") == "ok"


def test_quality_status_missing_translation():
    assert translation_quality_status(None, "\u539f\u6587") == "missing"
    assert translation_quality_status("   ", "\u539f\u6587") == "missing"


def test_quality_status_identical_to_raw_is_bad():
    raw = "\u539f\u6587\u5185\u5bb9"
    assert translation_quality_status(raw, raw) == "bad"


def test_quality_status_heavy_cjk_is_bad():
    raw = "\u8fd9\u662f\u4e00\u6bb5\u4e2d\u6587\u539f\u6587\u5185\u5bb9\uff0c\u5305\u542b\u591a\u884c\u53e5\u5b50\u3002"
    bad = (
        "\u8fd9\u662f\u4e00\u6bb5\u4e2d\u6587\u539f\u6587\u5185\u5bb9\uff0c\u5305\u542b\u591a\u884c\u53e5\u5b50\u3002"
        "\u8fd9\u662f\u53e6\u4e00\u6bb5\u5185\u5bb9\u3002\u8fd9\u662f\u7b2c\u4e09\u6bb5\u5185\u5bb9\u3002\u8fd9\u4e00\u6bb5\u4ecd\u7136\u5305\u542b\u4e2d\u6587\u3002"
        "多余内容 chính là tiếng Việt."
    )
    quality = translation_quality_status(bad, raw)
    assert quality == "bad"


def test_quality_status_a_few_cjk_is_warning():
    text = "B\u1ea3n d\u1ecbch c\u00f3 l\u1eabn v\u00e0i t\u1eeb H\u00e1n nh\u01b0 \u5e08\u5085 \u1edf \u0111\u00e2y th\u00f4i."
    quality = translation_quality_status(text, "\u539f\u6587")
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
    assert "nd-pill-error" in html
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
    assert "nd-pill-error" not in html
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
    assert "cr-alert-error" in html
    assert 'data-confirm-variant="warn"' in html
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
    assert 'action="/chapters/11/translate"' not in html
    assert "cr-alert-error" not in html


def test_severe_line_mismatch_raises():
    source = "\n".join(f"dòng gốc {i}" for i in range(30))
    translated = "Bản dịch bị cắt."
    try:
        _raise_if_severe_line_mismatch(source, translated, "test")
    except RuntimeError as exc:
        message = str(exc)
        assert "test" in message
        assert "30" in message
        assert "1" in message
    else:
        raise AssertionError("Expected severe line mismatch to raise")


def test_default_chunk_size_is_smaller_for_line_alignment():
    assert Settings().translation_max_chunk_chars == 600


def test_line_alignment_repair_accepts_matching_repair():
    class FakeProvider:
        def _chat(self, system_prompt, user_prompt, temperature):
            assert "Bản gốc tiếng Trung" in user_prompt
            assert temperature == 0.0
            return "Một\nHai\nBa"

    source = "一\n二\n三"
    translated = "Một\nHai\nBa\nBốn"
    repaired = _repair_line_alignment(FakeProvider(), source, translated, "chunk 1")

    assert repaired.text == "Một\nHai\nBa"
    assert repaired.warning
    assert "chunk 1" in repaired.warning


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


def test_provider_retries_remote_disconnect_once():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "Bản dịch sau khi thử lại."}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 6},
            }

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
                raise provider_mod.httpx.RemoteProtocolError(
                    "Server disconnected without sending a response."
                )
            return FakeResponse()

    original_client = provider_mod.httpx.Client
    original_sleep = provider_mod.time.sleep
    provider_mod.httpx.Client = FakeClient
    provider_mod.time.sleep = lambda _seconds: None
    try:
        provider = provider_mod.OpenAICompatProvider(
            name="openrouter",
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            model="google/gemini-2.5-flash-lite",
        )
        assert provider._chat("system", "user", temperature=0.0) == "Bản dịch sau khi thử lại."
        assert FakeClient.calls == 2
    finally:
        provider_mod.httpx.Client = original_client
        provider_mod.time.sleep = original_sleep


def test_provider_uses_reasoning_content_when_content_is_empty():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": "\n\n\u55ef...\n\nHứa Thanh nhìn về phía sa mạc trước mặt.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"completion_tokens": 12},
            }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            return FakeResponse()

    original_client = provider_mod.httpx.Client
    provider_mod.httpx.Client = FakeClient
    try:
        provider = provider_mod.OpenAICompatProvider(
            name="openrouter",
            api_key="test",
            base_url="https://openrouter.ai/api/v1",
            model="deepseek-v4-flash",
        )
        assert provider._chat("system", "user", temperature=0.0) == (
            "Hứa Thanh nhìn về phía sa mạc trước mặt."
        )
    finally:
        provider_mod.httpx.Client = original_client


def test_translate_chapter_translates_title_before_marking_done():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    seen_statuses: list[str] = []

    class FakeProvider:
        def translate(self, text, context):
            return "Dòng một\nDòng hai"

        def translate_metadata(self, text):
            seen_statuses.append(chapter.status)
            return "Chương 1: Tên đã dịch"

        def extract_terms(self, **kwargs):
            return []

        def summarize_chapter(self, **kwargs):
            return ""

    original_get_provider = glossary_mod.get_provider
    glossary_mod.get_provider = lambda session, provider_name: FakeProvider()
    try:
        with Session(engine) as session:
            novel = Novel(id=1, title="t", source_type="web")
            chapter = Chapter(
                id=1,
                novel_id=1,
                index=1,
                title="第1章 原题",
                raw_text="原文一\n原文二",
                status="fetched",
            )
            session.add(novel)
            session.add(chapter)
            session.commit()
            session.refresh(novel)
            session.refresh(chapter)

            result = translate_chapter(session, novel, chapter, provider_name="fake")

        assert seen_statuses == ["translating"]
        assert result.status == "translated"
        assert result.translated_title == "Chương 1: Tên đã dịch"
    finally:
        glossary_mod.get_provider = original_get_provider


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
    test_default_chunk_size_is_smaller_for_line_alignment()
    print("PASS test_default_chunk_size_is_smaller_for_line_alignment")
    test_line_alignment_repair_accepts_matching_repair()
    print("PASS test_line_alignment_repair_accepts_matching_repair")
    test_provider_rejects_length_finish_reason()
    print("PASS test_provider_rejects_length_finish_reason")
    test_provider_retries_finish_reason_error_once()
    print("PASS test_provider_retries_finish_reason_error_once")
    test_provider_retries_remote_disconnect_once()
    print("PASS test_provider_retries_remote_disconnect_once")
    test_provider_uses_reasoning_content_when_content_is_empty()
    print("PASS test_provider_uses_reasoning_content_when_content_is_empty")
    test_translate_chapter_translates_title_before_marking_done()
    print("PASS test_translate_chapter_translates_title_before_marking_done")
    print("\nAll 17 translation quality tests passed.")
