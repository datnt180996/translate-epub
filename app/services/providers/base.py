from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranslationContext:
    glossary: list[dict]
    style_guide: str
    previous_summaries: list[str]
    chapter_title: str = ""


class TranslationProvider(Protocol):
    name: str

    def translate(
        self,
        text: str,
        context: TranslationContext,
        system_prompt: str,
    ) -> str: ...

    def extract_terms(
        self,
        novel_title: str,
        chapter_title: str,
        original_text: str,
        translated_text: str,
    ) -> list[dict]: ...

    def summarize_chapter(
        self,
        novel_title: str,
        chapter_title: str,
        original_text: str,
        translated_text: str,
    ) -> str: ...
