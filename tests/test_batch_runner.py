"""Tests for batch_translation_runner eligibility & registry behavior."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_db() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return tmp.name


def test_filter_eligible_orders_by_index_and_skips_translated():
    db_path = _fresh_db()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    import app.config as cfg
    cfg.get_settings.cache_clear()
    import app.db as db
    importlib.reload(db)
    import app.models as models  # noqa: F401
    db.init_db()

    from app.models import Chapter, Novel
    from sqlmodel import Session

    with Session(db.engine) as session:
        novel = Novel(title="T", source_type="web", source_url="x")
        session.add(novel)
        session.commit()
        session.refresh(novel)
        novel_id = novel.id
        c1 = Chapter(novel_id=novel.id, index=1, title="c1", status="fetched", raw_text="r1")
        c2 = Chapter(novel_id=novel.id, index=2, title="c2", status="fetched", raw_text="r2", translated_text="đã dịch")
        c3 = Chapter(novel_id=novel.id, index=3, title="c3", status="fetched", raw_text="r3")
        c4 = Chapter(novel_id=novel.id, index=4, title="c4", status="translating", raw_text="r4")
        c5 = Chapter(novel_id=novel.id, index=5, title="c5", status="fetched")
        c6 = Chapter(novel_id=novel.id, index=6, title="c6", status="fetched", raw_text="r6")
        session.add_all([c1, c2, c3, c4, c5, c6])
        session.commit()
        ids = {c1.id, c2.id, c3.id, c4.id, c5.id, c6.id}

    import app.services.batch_translation_runner as runner
    importlib.reload(runner)

    eligible = runner.filter_eligible_for_novel(
        novel_id, list(ids)
    )
    assert eligible == [c1.id, c3.id, c6.id]
    db.engine.dispose()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_eligible_count_for_novel_matches_filter():
    db_path = _fresh_db()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    import app.config as cfg
    cfg.get_settings.cache_clear()
    import app.db as db
    importlib.reload(db)
    import app.models as models  # noqa: F401
    db.init_db()

    from app.models import Chapter, Novel
    from sqlmodel import Session

    with Session(db.engine) as session:
        novel = Novel(title="T", source_type="web", source_url="x")
        session.add(novel)
        session.commit()
        session.refresh(novel)
        novel_id = novel.id
        for idx in range(5):
            session.add(
                Chapter(novel_id=novel_id, index=idx + 1, title=f"c{idx}", status="fetched", raw_text=f"r{idx}")
            )
        session.add(
            Chapter(novel_id=novel_id, index=6, title="done", status="translated", raw_text="r6", translated_text="d6")
        )
        session.commit()

    import app.services.batch_translation_runner as runner
    importlib.reload(runner)

    count = runner.eligible_count_for_novel(novel_id)
    assert count == 5
    db.engine.dispose()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_start_batch_refuses_duplicate_for_same_novel():
    import app.services.batch_translation_runner as runner

    runner._tasks.pop(99, None)

    stop = threading.Event()

    def _long_running():
        stop.wait(timeout=15)

    thread = threading.Thread(target=_long_running, daemon=True)
    thread.start()
    runner._tasks[99] = runner._RunningBatchTask(novel_id=99, chapter_ids=[1, 2], provider="minimax", thread=thread)
    try:
        with runner._lock:
            t = runner._tasks.get(99)
            assert t is not None and t.thread.is_alive()
        ok, _ = runner.start_batch_translation(99, [3, 4], "minimax")
        assert ok is False
    finally:
        stop.set()
        runner._tasks.pop(99, None)


if __name__ == "__main__":
    test_filter_eligible_orders_by_index_and_skips_translated()
    print("PASS test_filter_eligible_orders_by_index_and_skips_translated")
    test_eligible_count_for_novel_matches_filter()
    print("PASS test_eligible_count_for_novel_matches_filter")
    test_start_batch_refuses_duplicate_for_same_novel()
    print("PASS test_start_batch_refuses_duplicate_for_same_novel")
    print("\nAll 3 batch runner tests passed.")
