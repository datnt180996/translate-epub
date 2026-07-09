from __future__ import annotations

import re
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Optional

from sqlmodel import Session, select

from ..config import get_settings
from ..models import Chapter, ChapterSummary, GlossaryTerm, Novel, StyleGuide
from .chapter_cleaner import chunk_text, count_non_empty_lines, line_count_mismatch, strip_chapter_boilerplate
from .providers.base import TranslationContext
from .providers.factory import get_provider
from .providers.minimax import (
    CLEANUP_PROMPT,
    LINE_ALIGNMENT_PROMPT,
    contains_cjk,
    find_cjk_spans,
)
from . import translation_jobs as jobs


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CJK_COUNT_LIMIT = 20
CJK_RATIO_LIMIT = 0.05


@dataclass
class AlignmentRepairResult:
    text: str
    warning: Optional[str] = None


def _severe_line_count_mismatch(source_lines: int, translated_lines: int) -> bool:
    if source_lines <= 0:
        return False
    if translated_lines <= 0:
        return True
    if source_lines <= 4:
        return abs(source_lines - translated_lines) > 1
    if translated_lines < int(source_lines * 0.85):
        return True
    if abs(source_lines - translated_lines) > 10:
        return True
    return False


def _raise_if_severe_line_mismatch(source_text: str, translated_text: str, label: str) -> None:
    source_lines, translated_lines = line_count_mismatch(source_text, translated_text)
    if _severe_line_count_mismatch(source_lines, translated_lines):
        raise RuntimeError(
            f"Bản dịch thiếu/lệch dòng nghiêm trọng ở {label}: "
            f"gốc {source_lines} dòng, dịch {translated_lines} dòng. "
            "Không lưu bản dịch vì có thể bị cắt hoặc bỏ sót nội dung."
        )

def _repair_line_alignment(
    provider,
    source_text: str,
    translated_text: str,
    label: str,
) -> AlignmentRepairResult:
    src_lines, tgt_lines = line_count_mismatch(source_text, translated_text)
    if src_lines == tgt_lines:
        return AlignmentRepairResult(translated_text)

    repair_user = (
        f"### Bản gốc tiếng Trung\n{source_text}\n\n"
        f"### Bản dịch tiếng Việt\n{translated_text}"
    )
    repaired = provider._chat(LINE_ALIGNMENT_PROMPT, repair_user, temperature=0.0).strip()
    if not repaired:
        return AlignmentRepairResult(
            translated_text,
            f"{label}: không sửa được căn dòng vì provider trả về rỗng",
        )

    repaired_quality = translation_quality_status(repaired, source_text)
    repaired_cjk = len(_CJK_RE.findall(repaired))
    pre_repair_cjk = len(_CJK_RE.findall(translated_text))
    new_src, new_tgt = line_count_mismatch(source_text, repaired)
    if (
        new_src == new_tgt
        and new_src > 0
        and repaired_quality != "bad"
        and repaired_cjk <= max(pre_repair_cjk, 1)
    ):
        return AlignmentRepairResult(
            repaired,
            f"{label}: đã tự căn lại dòng (trước: {src_lines}/{tgt_lines}, sau: {new_src}/{new_tgt})",
        )

    return AlignmentRepairResult(
        translated_text,
        f"{label}: tự căn dòng chưa đạt (gốc: {src_lines}, dịch: {tgt_lines}, sau sửa: {new_tgt})",
    )


def translation_quality_status(translated_text: Optional[str], raw_text: Optional[str]) -> str:
    """Classify a translation result.

    Returns one of:
    - ``missing``: empty or only whitespace.
    - ``bad``: identical to raw_text, or too many CJK characters survived.
    - ``warning``: a few CJK characters survived but below bad threshold.
    - ``ok``: no CJK characters detected.
    """
    if not translated_text or not translated_text.strip():
        return "missing"
    cjk_count = len(_CJK_RE.findall(translated_text))
    length = max(len(translated_text), 1)
    ratio = cjk_count / length
    if raw_text and translated_text.strip() == raw_text.strip():
        return "bad"
    if cjk_count >= CJK_COUNT_LIMIT and ratio >= CJK_RATIO_LIMIT:
        return "bad"
    if cjk_count > 0:
        return "warning"
    return "ok"


def get_style_guide(session: Session, novel_id: int) -> str:
    guide = session.exec(select(StyleGuide).where(StyleGuide.novel_id == novel_id)).first()
    return guide.guide_text if guide else ""


def set_style_guide(session: Session, novel_id: int, guide_text: str) -> StyleGuide:
    guide = session.exec(select(StyleGuide).where(StyleGuide.novel_id == novel_id)).first()
    if guide is None:
        guide = StyleGuide(novel_id=novel_id, guide_text=guide_text)
        session.add(guide)
    else:
        guide.guide_text = guide_text
    session.commit()
    session.refresh(guide)
    return guide


def list_glossary(session: Session, novel_id: int) -> list[GlossaryTerm]:
    return list(session.exec(select(GlossaryTerm).where(GlossaryTerm.novel_id == novel_id)).all())


def glossary_to_context(terms: list[GlossaryTerm]) -> list[dict]:
    return [
        {
            "source": t.source_text,
            "target": t.target_text,
            "category": t.category,
        }
        for t in terms
    ]


def add_term(session: Session, novel_id: int, source: str, target: str, category: str = "general", notes: Optional[str] = None) -> GlossaryTerm:
    term = GlossaryTerm(
        novel_id=novel_id,
        source_text=source.strip(),
        target_text=target.strip(),
        category=category.strip() or "general",
        notes=notes,
    )
    session.add(term)
    session.commit()
    session.refresh(term)
    return term


def delete_term(session: Session, term_id: int) -> None:
    term = session.get(GlossaryTerm, term_id)
    if term is not None:
        session.delete(term)
        session.commit()


def list_recent_summaries(session: Session, novel_id: int, limit: int = 5) -> list[str]:
    rows = session.exec(
        select(ChapterSummary)
        .where(ChapterSummary.novel_id == novel_id)
        .order_by(ChapterSummary.id.desc())
        .limit(limit)
    ).all()
    return [r.summary for r in reversed(rows)]


def build_translation_context(session: Session, novel: Novel, chapter: Chapter) -> TranslationContext:
    terms = list_glossary(session, novel.id)
    style = get_style_guide(session, novel.id)
    summaries = list_recent_summaries(session, novel.id, limit=5)
    return TranslationContext(
        glossary=glossary_to_context(terms),
        style_guide=style,
        previous_summaries=summaries,
        chapter_title=chapter.title,
    )


def translate_chapter(
    session: Session,
    novel: Novel,
    chapter: Chapter,
    provider_name: str,
    max_chunk_chars: Optional[int] = None,
) -> Chapter:
    if not chapter.raw_text:
        raise ValueError("Chương chưa có nội dung gốc. Hãy fetch trước khi dịch.")

    settings = get_settings()
    if max_chunk_chars is None:
        max_chunk_chars = settings.translation_max_chunk_chars

    provider = get_provider(session, provider_name)
    context = build_translation_context(session, novel, chapter)
    source_text = strip_chapter_boilerplate(chapter.raw_text, chapter.title) or chapter.raw_text

    chunks = chunk_text(source_text, max_chars=max_chunk_chars)

    chapter.status = "translating"
    chapter.error_message = None
    chapter.translation_warning = None
    chapter.failed_translation_draft = None
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    jobs.mark_running(session, chapter.id, total_chunks=len(chunks))

    concurrency = max(1, min(settings.translation_concurrency, len(chunks) or 1))

    failed_drafts_by_index: dict[int, str] = {}
    draft_lock = Lock()

    def _add_warning(existing: Optional[str], message: str) -> str:
        return message if existing is None else f"{existing}; {message}"

    def _translate_one(idx: int) -> tuple[int, str, Optional[str]]:
        translated = provider.translate(chunks[idx], context=context)
        if not translated or not translated.strip():
            raise RuntimeError(f"Provider trả về chunk dịch rỗng (chunk {idx + 1}).")
        warning: Optional[str] = None
        if contains_cjk(translated):
            try:
                cleaned = provider._chat(
                    CLEANUP_PROMPT,
                    translated,
                    temperature=0.0,
                ).strip()
                if cleaned:
                    translated = cleaned
            except Exception as cleanup_exc:  # noqa: BLE001
                warning = f"chunk {idx + 1}: cleanup lỗi ({cleanup_exc})"
        if contains_cjk(translated):
            examples = "".join(find_cjk_spans(translated))
            warning = (
                f"chunk {idx + 1}: còn sót chữ Hán ({examples})"
                if warning is None
                else f"{warning}; vẫn còn chữ Hán ({examples})"
            )
        label = f"chunk {idx + 1}"
        src_lines, tgt_lines = line_count_mismatch(chunks[idx], translated)
        if src_lines != tgt_lines:
            try:
                repaired = _repair_line_alignment(provider, chunks[idx], translated, label)
                translated = repaired.text
                if repaired.warning:
                    warning = _add_warning(warning, repaired.warning)
            except Exception as repair_exc:  # noqa: BLE001
                warning = _add_warning(warning, f"{label}: tự căn dòng lỗi ({repair_exc})")
        try:
            _raise_if_severe_line_mismatch(chunks[idx], translated, label)
        except RuntimeError:
            with draft_lock:
                failed_drafts_by_index[idx] = translated
            raise
        return idx, translated, warning

    translated_by_index: dict[int, str] = {}
    warnings_by_index: dict[int, Optional[str]] = {}

    try:
        if concurrency <= 1 or len(chunks) <= 1:
            for i in range(len(chunks)):
                idx, txt, warn = _translate_one(i)
                translated_by_index[idx] = txt
                warnings_by_index[idx] = warn
                jobs.increment_progress(session, chapter.id, failed=bool(warn and "còn sót chữ Hán" in warn))
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_translate_one, i): i for i in range(len(chunks))}
                for fut in as_completed(futures):
                    idx, txt, warn = fut.result()
                    translated_by_index[idx] = txt
                    warnings_by_index[idx] = warn
                    jobs.increment_progress(session, chapter.id, failed=bool(warn and "còn sót chữ Hán" in warn))
    except Exception as e:
        chapter.status = "error"
        chapter.error_message = str(e)
        if failed_drafts_by_index:
            chapter.failed_translation_draft = "\n\n".join(
                f"--- chunk {i + 1} ---\n{failed_drafts_by_index[i]}"
                for i in sorted(failed_drafts_by_index)
            )
        session.add(chapter)
        session.commit()
        jobs.mark_error(session, chapter.id, str(e))
        raise

    translated_chunks = [translated_by_index[i] for i in range(len(chunks))]
    translated_text = "\n".join(c for c in translated_chunks if c)

    alignment_warning: Optional[str] = None
    src_lines, tgt_lines = line_count_mismatch(source_text, translated_text)
    if src_lines != tgt_lines:
        try:
            repair_user = (
                f"### Bản gốc tiếng Trung\n{source_text}\n\n"
                f"### Bản dịch tiếng Việt\n{translated_text}"
            )
            repaired = provider._chat(
                LINE_ALIGNMENT_PROMPT, repair_user, temperature=0.0
            ).strip()
            if repaired:
                repaired_quality = translation_quality_status(repaired, source_text)
                repaired_cjk = len(_CJK_RE.findall(repaired))
                pre_repair_cjk = len(_CJK_RE.findall(translated_text))
                line_ok = False
                new_src, new_tgt = line_count_mismatch(source_text, repaired)
                line_ok = new_src == new_tgt and new_src > 0
                if (
                    line_ok
                    and repaired_quality != "bad"
                    and repaired_cjk <= max(pre_repair_cjk, 1)
                ):
                    translated_text = repaired
                    src_lines, tgt_lines = new_src, new_tgt
                else:
                    alignment_warning = (
                        f"Bản dịch không khớp số dòng gốc (gốc: {src_lines}, "
                        f"dịch: {tgt_lines}, sau repair: {new_tgt})"
                    )
        except Exception as repair_exc:  # noqa: BLE001
            alignment_warning = (
                f"Bản dịch không khớp số dòng gốc (gốc: {src_lines}, dịch: {tgt_lines}); "
                f"repair lỗi ({repair_exc})"
            )

        if alignment_warning is None and src_lines != tgt_lines:
            alignment_warning = (
                f"Bản dịch không khớp số dòng gốc (gốc: {src_lines}, dịch: {tgt_lines})"
            )

    try:
        _raise_if_severe_line_mismatch(source_text, translated_text, "toàn chương")
    except RuntimeError as mismatch_exc:
        chapter.status = "error"
        chapter.error_message = str(mismatch_exc)
        chapter.failed_translation_draft = translated_text
        session.add(chapter)
        session.commit()
        jobs.mark_error(session, chapter.id, chapter.error_message)
        raise

    warnings = [w for w in (warnings_by_index[i] for i in range(len(chunks))) if w]
    if alignment_warning:
        warnings.append(alignment_warning)
    if warnings:
        chapter.translation_warning = "Bản dịch có cảnh báo: " + "; ".join(warnings)

    if not translated_text or not translated_text.strip():
        chapter.status = "error"
        chapter.error_message = "Bản dịch rỗng sau khi ghép chunks."
        session.add(chapter)
        session.commit()
        jobs.mark_error(session, chapter.id, chapter.error_message)
        raise RuntimeError("Bản dịch rỗng sau khi ghép chunks.")

    quality = translation_quality_status(translated_text, source_text)
    if quality == "bad":
        chapter.status = "error"
        chapter.failed_translation_draft = translated_text
        chapter.error_message = (
            "Bản dịch còn quá nhiều chữ Hán hoặc giống bản gốc. "
            "Vui lòng dịch lại."
        )
        chapter.translation_warning = None
        session.add(chapter)
        session.commit()
        jobs.mark_error(session, chapter.id, chapter.error_message)
        raise RuntimeError(chapter.error_message)

    from datetime import datetime

    if not chapter.translated_title and chapter.title:
        try:
            translated_title = provider.translate_metadata(chapter.title)
        except Exception:
            translated_title = ""
        if translated_title:
            chapter.translated_title = translated_title

    chapter.translated_text = translated_text
    chapter.failed_translation_draft = None
    chapter.translation_provider = provider_name
    chapter.status = "translated"
    chapter.updated_at = datetime.utcnow()
    session.add(chapter)
    jobs.mark_done(session, chapter.id)
    session.commit()
    session.refresh(chapter)

    if settings.auto_extract_glossary:
        try:
            terms = provider.extract_terms(
                novel_title=novel.title,
                chapter_title=chapter.title,
                original_text=source_text,
                translated_text=translated_text,
            )
            for term in terms:
                exists = session.exec(
                    select(GlossaryTerm).where(
                        (GlossaryTerm.novel_id == novel.id)
                        & (GlossaryTerm.source_text == term["source"])
                    )
                ).first()
                if exists is None:
                    session.add(
                        GlossaryTerm(
                            novel_id=novel.id,
                            source_text=term["source"],
                            target_text=term["target"],
                            category=term.get("category", "other"),
                        )
                    )
        except Exception:
            pass

    if settings.auto_summarize_chapter:
        try:
            summary = provider.summarize_chapter(
                novel_title=novel.title,
                chapter_title=chapter.title,
                original_text=source_text,
                translated_text=translated_text,
            )
            if summary:
                session.add(ChapterSummary(novel_id=novel.id, chapter_id=chapter.id, summary=summary))
        except Exception:
            pass

    session.commit()
    session.refresh(chapter)
    return chapter
