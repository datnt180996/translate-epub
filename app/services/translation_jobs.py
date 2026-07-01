from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..models import TranslationJob


def get_or_create(session: Session, chapter_id: int, novel_id: int, provider: str) -> TranslationJob:
    job = session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()
    if job is None:
        job = TranslationJob(chapter_id=chapter_id, novel_id=novel_id, provider=provider)
        session.add(job)
    else:
        job.novel_id = novel_id
        job.provider = provider
        session.add(job)
    session.commit()
    session.refresh(job)
    return job


def reset(session: Session, chapter_id: int, novel_id: Optional[int] = None, provider: str = "") -> TranslationJob:
    job = session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()
    now = datetime.utcnow()
    if job is None:
        job = TranslationJob(
            chapter_id=chapter_id,
            novel_id=novel_id or 0,
            provider=provider,
            status="queued",
            total_chunks=0,
            done_chunks=0,
            failed_chunks=0,
            current_chunk=0,
            error_message=None,
            started_at=now,
            updated_at=now,
        )
        session.add(job)
    else:
        if novel_id:
            job.novel_id = novel_id
        if provider:
            job.provider = provider
        job.status = "queued"
        job.total_chunks = 0
        job.done_chunks = 0
        job.failed_chunks = 0
        job.current_chunk = 0
        job.error_message = None
        job.started_at = now
        job.updated_at = now
    session.commit()
    session.refresh(job)
    return job


def mark_running(session: Session, chapter_id: int, total_chunks: int) -> Optional[TranslationJob]:
    job = session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()
    if job is None:
        return None
    job.status = "running"
    job.total_chunks = total_chunks
    job.done_chunks = 0
    job.failed_chunks = 0
    job.current_chunk = 0
    job.started_at = job.started_at or datetime.utcnow()
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def increment_progress(session: Session, chapter_id: int, failed: bool = False) -> Optional[TranslationJob]:
    job = session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()
    if job is None:
        return None
    if failed:
        job.failed_chunks += 1
    else:
        job.done_chunks += 1
    job.current_chunk = job.done_chunks + job.failed_chunks
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_done(session: Session, chapter_id: int) -> Optional[TranslationJob]:
    job = session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()
    if job is None:
        return None
    job.status = "done"
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_error(session: Session, chapter_id: int, error: str) -> Optional[TranslationJob]:
    job = session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()
    if job is None:
        return None
    job.status = "error"
    job.error_message = error
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get(session: Session, chapter_id: int) -> Optional[TranslationJob]:
    return session.exec(
        select(TranslationJob).where(TranslationJob.chapter_id == chapter_id)
    ).first()