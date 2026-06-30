from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, List, TypeVar

T = TypeVar("T")


_PRE_PATTERNS = [
    re.compile(r"序章|序言|楔子|前言", re.IGNORECASE),
]

_POST_PATTERNS = [
    (re.compile(r"番外", re.IGNORECASE), 30),
    (re.compile(r"后记|後記", re.IGNORECASE), 31),
    (re.compile(r"外传|外傳", re.IGNORECASE), 32),
    (re.compile(r"结语|結語|终章|終章", re.IGNORECASE), 33),
    (re.compile(r"附录|附錄", re.IGNORECASE), 34),
]

_MAIN_PATTERNS = [
    re.compile(r"第\s*([0-9零一二三四五六七八九十百千万萬兩两]+)\s*[章回节節卷部篇]", re.IGNORECASE),
    re.compile(r"第\s*([0-9零一二三四五六七八九十百千万萬兩两]+)\s*话話", re.IGNORECASE),
    re.compile(r"chapter\s*([0-9]+)", re.IGNORECASE),
    re.compile(r"^([0-9]+)[\s\.\-、]"),
    re.compile(r"\s([0-9]+)\s*$"),
]

_CN_DIGIT_MAP = {
    "零": 0, "一": 1, "二": 2, "两": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "百": 100, "千": 1000, "万": 10000, "萬": 10000,
}


def _cn_to_int(s: str) -> int | None:
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if not all(c in _CN_DIGIT_MAP for c in s):
        return None
    total = 0
    current = 0
    for c in s:
        v = _CN_DIGIT_MAP[c]
        if v >= 10:
            if current == 0:
                current = 1
            total += current * v
            current = 0
        else:
            current = v
    total += current
    return total if total > 0 else None


@dataclass(frozen=True)
class ChapterSortKey:
    group: int            # 0=pre, 1=main, 2=post-extras
    primary: int          # chapter number for main, category priority for pre/post
    secondary: int        # original order fallback

    def __lt__(self, other: "ChapterSortKey") -> bool:
        if self.group != other.group:
            return self.group < other.group
        if self.primary != other.primary:
            return self.primary < other.primary
        return self.secondary < other.secondary


def chapter_sort_key(title: str, original_index: int) -> ChapterSortKey:
    text = (title or "").strip()

    for pattern in _PRE_PATTERNS:
        if pattern.search(text):
            return ChapterSortKey(group=0, primary=0, secondary=original_index)

    for pattern, priority in _POST_PATTERNS:
        if pattern.search(text):
            return ChapterSortKey(group=2, primary=priority, secondary=original_index)

    for pattern in _MAIN_PATTERNS:
        m = pattern.search(text)
        if m:
            n = _cn_to_int(m.group(1))
            if n is not None:
                return ChapterSortKey(group=1, primary=n, secondary=original_index)

    return ChapterSortKey(group=2, primary=40, secondary=original_index)


def sort_chapters(items: Iterable[T], title_of: Callable[[T], str]) -> List[T]:
    indexed = list(enumerate(items))
    return [
        item
        for _, item in sorted(
            indexed,
            key=lambda pair: chapter_sort_key(title_of(pair[1]), pair[0]),
        )
    ]