from __future__ import annotations

import re
from bs4 import BeautifulSoup


def clean_html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def split_into_paragraphs(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p and p.strip()]


def join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())


def split_into_lines(text: str) -> list[str]:
    """Split text into lines preserving empty lines (which represent paragraph
    breaks in the original source)."""
    if not text:
        return []
    return text.split("\n")


def join_lines(lines: list[str]) -> str:
    """Join lines back with ``\n`` separator, dropping trailing empty lines."""
    cleaned = [ln for ln in lines]
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


def count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.split("\n"))


def count_non_empty_lines(text: str) -> int:
    if not text:
        return 0
    return sum(1 for line in text.split("\n") if line.strip())


def chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    """Split text into chunks for translation.

    Strategy:
    - Split into lines first (one source line = one translation line).
    - Each chunk holds whole lines until adding the next one would exceed
      ``max_chars``.
    - If a single line exceeds ``max_chars``, it is hard-split by characters.
      Empty lines are preserved across chunks so paragraph breaks in the
      source remain intact after chunks are rejoined.
    """
    lines = split_into_lines(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line)
        if line_len > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, line_len, max_chars):
                chunks.append(line[i : i + max_chars])
            continue

        addition = line_len + (1 if current else 0)
        if current and current_len + addition > max_chars:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += addition

    if current:
        chunks.append("\n".join(current))

    return [c for c in chunks if c is not None]


def line_count_mismatch(source_text: str, translated_text: str) -> tuple[int, int]:
    """Compare non-empty line counts between source and translation.

    Returns ``(source_count, translated_count)``. When the counts are equal
    the translation is considered well-aligned with the source.
    """
    return count_non_empty_lines(source_text), count_non_empty_lines(translated_text)