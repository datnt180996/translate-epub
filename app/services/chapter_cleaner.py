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
            for i in range(0, len(p), max_chars):
                chunks.append(p[i : i + max_chars])
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
