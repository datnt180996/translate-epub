from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from sqlmodel import Session, select

from ..config import get_settings
from ..models import Chapter, ChapterSummary, GlossaryTerm, Novel, StyleGuide
from .chapter_cleaner import chunk_text, join_paragraphs, split_into_paragraphs
from .providers.base import TranslationContext
from .providers.factory import get_provider


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

    provider = get_provider(provider_name)
    context = build_translation_context(session, novel, chapter)

    chunks = chunk_text(chapter.raw_text, max_chars=max_chunk_chars)

    chapter.status = "translating"
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    concurrency = max(1, min(settings.translation_concurrency, len(chunks) or 1))

    def _translate_one(idx: int) -> tuple[int, str]:
        translated = provider.translate(chunks[idx], context=context)
        if not translated or not translated.strip():
            raise RuntimeError(f"Provider trả về chunk dịch rỗng (chunk {idx + 1}).")
        return idx, translated

    translated_by_index: dict[int, str] = {}

    try:
        if concurrency <= 1 or len(chunks) <= 1:
            for i in range(len(chunks)):
                idx, txt = _translate_one(i)
                translated_by_index[idx] = txt
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(_translate_one, i) for i in range(len(chunks))]
                for fut in futures:
                    idx, txt = fut.result()
                    translated_by_index[idx] = txt
    except Exception:
        chapter.status = "error"
        session.add(chapter)
        session.commit()
        raise

    translated_chunks = [translated_by_index[i] for i in range(len(chunks))]
    translated_text = join_paragraphs(translated_chunks)

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
