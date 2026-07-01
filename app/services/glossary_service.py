from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from sqlmodel import Session, select

from ..config import get_settings
from ..models import Chapter, ChapterSummary, GlossaryTerm, Novel, StyleGuide
from .chapter_cleaner import chunk_text, count_non_empty_lines, line_count_mismatch
from .providers.base import TranslationContext
from .providers.factory import get_provider
from .providers.minimax import (
    CLEANUP_PROMPT,
    LINE_ALIGNMENT_PROMPT,
    contains_cjk,
    find_cjk_spans,
)
from . import translation_jobs as jobs


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

    chunks = chunk_text(chapter.raw_text, max_chars=max_chunk_chars)

    chapter.status = "translating"
    chapter.translation_warning = None
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    jobs.mark_running(session, chapter.id, total_chunks=len(chunks))

    concurrency = max(1, min(settings.translation_concurrency, len(chunks) or 1))

    def _translate_one(idx: int) -> tuple[int, str]:
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
        session.add(chapter)
        session.commit()
        jobs.mark_error(session, chapter.id, str(e))
        raise

    translated_chunks = [translated_by_index[i] for i in range(len(chunks))]
    translated_text = "\n".join(c for c in translated_chunks if c)

    alignment_warning: Optional[str] = None
    src_lines, tgt_lines = line_count_mismatch(chapter.raw_text, translated_text)
    if src_lines != tgt_lines:
        try:
            repair_user = (
                f"### Bản gốc tiếng Trung\n{chapter.raw_text}\n\n"
                f"### Bản dịch tiếng Việt\n{translated_text}"
            )
            repaired = provider._chat(
                LINE_ALIGNMENT_PROMPT, repair_user, temperature=0.0
            ).strip()
            if repaired:
                new_src, new_tgt = line_count_mismatch(chapter.raw_text, repaired)
                if new_src == new_tgt and new_src > 0:
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

    warnings = [w for w in (warnings_by_index[i] for i in range(len(chunks))) if w]
    if alignment_warning:
        warnings.append(alignment_warning)
    if warnings:
        chapter.translation_warning = "Bản dịch có cảnh báo: " + "; ".join(warnings)

    if not translated_text or not translated_text.strip():
        chapter.status = "error"
        session.add(chapter)
        session.commit()
        raise RuntimeError("Bản dịch rỗng sau khi ghép chunks.")

    chapter.translated_text = translated_text
    chapter.translation_provider = provider_name
    chapter.status = "translated"
    from datetime import datetime
    chapter.updated_at = datetime.utcnow()
    session.add(chapter)
    jobs.mark_done(session, chapter.id)
    session.commit()
    session.refresh(chapter)

    if not chapter.translated_title and chapter.title:
        try:
            translated_title = provider.translate_metadata(chapter.title)
        except Exception:
            translated_title = ""
        if translated_title:
            chapter.translated_title = translated_title
            chapter.updated_at = datetime.utcnow()
            session.add(chapter)
            session.commit()
            session.refresh(chapter)

    if settings.auto_extract_glossary:
        try:
            terms = provider.extract_terms(
                novel_title=novel.title,
                chapter_title=chapter.title,
                original_text=chapter.raw_text,
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
                original_text=chapter.raw_text,
                translated_text=translated_text,
            )
            if summary:
                session.add(ChapterSummary(novel_id=novel.id, chapter_id=chapter.id, summary=summary))
        except Exception:
            pass

    session.commit()
    session.refresh(chapter)
    return chapter
