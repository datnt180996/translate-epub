from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Novel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    translated_title: Optional[str] = None
    author: Optional[str] = None
    source_type: str
    source_url: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    translated_author: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    novel_id: int = Field(foreign_key="novel.id", index=True)
    index: int
    title: str
    translated_title: Optional[str] = None
    source_url: Optional[str] = None
    raw_text: Optional[str] = None
    translated_text: Optional[str] = None
    failed_translation_draft: Optional[str] = None
    translation_provider: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None
    translation_warning: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GlossaryTerm(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    novel_id: int = Field(foreign_key="novel.id", index=True)
    source_text: str
    target_text: str
    category: str = "general"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChapterSummary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    novel_id: int = Field(foreign_key="novel.id", index=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    summary: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StyleGuide(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    novel_id: int = Field(foreign_key="novel.id", index=True, unique=True)
    guide_text: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProviderSetting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True, unique=True)
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    group_id: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TranslationJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True, unique=True)
    novel_id: int = Field(foreign_key="novel.id", index=True)
    provider: str = ""
    status: str = "queued"  # queued | running | done | error
    total_chunks: int = 0
    done_chunks: int = 0
    failed_chunks: int = 0
    current_chunk: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
