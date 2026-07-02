"""One-off cleanup script for bad-quality translations.

Identifies chapters whose translated_text equals raw_text or contains a high
ratio of CJK characters, then resets them so the UI no longer marks them as
``translated``. Existing translated_text is preserved for inspection but the
status is moved to ``error`` so a retry button can be surfaced.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, select

from app.db import engine
from app.models import Chapter
from app.services.glossary_service import translation_quality_status


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def main() -> int:
    reset = 0
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(Chapter).where(Chapter.translated_text.is_not(None))
            ).all()
        )
        for ch in rows:
            quality = translation_quality_status(ch.translated_text, ch.raw_text)
            if quality == "bad":
                ch.status = "error"
                ch.error_message = (
                    "Bản dịch còn quá nhiều chữ Hán hoặc giống bản gốc. "
                    "Hãy dịch lại."
                )
                ch.translation_warning = None
                ch.translated_text = None
                ch.translated_title = None
                session.add(ch)
                reset += 1
        if reset:
            session.commit()
    print(f"Reset {reset} bad-quality chapters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
