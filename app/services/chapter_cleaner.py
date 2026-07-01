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


def chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    """Split text into chunks for translation.

    Strategy:
    - Split into paragraphs first (paragraphs are natural translation units).
    - Each chunk holds whole paragraphs until adding the next one would exceed
      ``max_chars``.
    - If a single paragraph exceeds ``max_chars``, split it by sentence
      boundary (Chinese/Vietnamese punctuation), then by characters as a
      fallback. This avoids breaking the translation flow mid-sentence.
    """
    paragraphs = split_into_paragraphs(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for p in paragraphs:
        if len(p) > max_chars:
            if current:
                chunks.append(join_paragraphs(current))
                current = []
                current_len = 0
            for piece in _split_long_paragraph(p, max_chars):
                chunks.append(piece)
            continue

        if current_len + len(p) + 2 > max_chars and current:
            chunks.append(join_paragraphs(current))
            current = [p]
            current_len = len(p)
        else:
            current.append(p)
            current_len += len(p) + 2

    if current:
        chunks.append(join_paragraphs(current))

    return chunks


_SENTENCE_END = re.compile(r"(?<=[\.。!?！？;；:：])\s*")


def _split_long_paragraph(p: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph by sentence, then by characters."""
    pieces = [s.strip() for s in _SENTENCE_END.split(p) if s and s.strip()]
    if not pieces:
        pieces = [p]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for s in pieces:
        if len(s) > max_chars:
            if current:
                chunks.append("".join(current).strip())
                current = []
                current_len = 0
            for i in range(0, len(s), max_chars):
                chunks.append(s[i : i + max_chars])
            continue
        if current_len + len(s) + 1 > max_chars and current:
            chunks.append("".join(current).strip())
            current = [s]
            current_len = len(s)
        else:
            current.append(s)
            current_len += len(s) + 1

    if current:
        chunks.append("".join(current).strip())
    return [c for c in chunks if c]
