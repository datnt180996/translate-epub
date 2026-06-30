from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Novel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: Optional[str] = None
    source_type: str
    source_url: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    novel_id: int = Field(foreign_key="novel.id", index=True)
    index: int
    title: str
    source_url: Optional[str] = None
    raw_text: Optional[str] = None
    translated_text: Optional[str] = None
    translation_provider: Optional[str] = None
    status: str = "pending"
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
