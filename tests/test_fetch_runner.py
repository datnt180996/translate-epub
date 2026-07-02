"""Tests for the auto-fetch runner: registry dedup, cleanup, batch claim."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_db() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return tmp.name


def test_start_fetch_all_refuses_duplicate_job(monkeypatch=None):
    db_path = _fresh_db()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    import app.config as cfg
    cfg.get_settings.cache_clear()
    import app.services.fetch_runner as runner
    importlib.reload(runner)

    blocked = []
    runner._tasks[1] = runner._RunningFetchTask(novel_id=1, thread=_always_alive_thread())
    try:
        ok = runner.start_fetch_all(1)
        assert ok is False
    finally:
        runner._tasks.pop(1, None)
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_cleanup_stale_fetching_resets_pending_chapters():
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
        novel = Novel(title="Test", source_type="web", source_url="x")
        session.add(novel)
        session.commit()
        session.refresh(novel)
        ch1 = Chapter(novel_id=novel.id, index=1, title="第1章", source_url="https://example.com/1", status="fetching")
        ch2 = Chapter(novel_id=novel.id, index=2, title="第2章", source_url="https://example.com/2", status="fetching", raw_text="đã có")
        session.add(ch1)
        session.add(ch2)
        session.commit()

    import app.services.fetch_runner as runner
    importlib.reload(runner)
    reset = runner.cleanup_stale_fetching()
    assert reset == 1

    with Session(db.engine) as session:
        ch1 = session.exec(__import__("sqlmodel").select(Chapter).where(Chapter.index == 1)).first()
        ch2 = session.exec(__import__("sqlmodel").select(Chapter).where(Chapter.index == 2)).first()
        assert ch1.status == "pending"
        assert ch2.status == "fetched"
        assert ch1.error_message and "restart" in ch1.error_message.lower()

    db.engine.dispose()
    if os.path.exists(db_path):
        os.unlink(db_path)


def _always_alive_thread():
    import threading

    def _run():
        import time
        time.sleep(60)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    test_start_fetch_all_refuses_duplicate_job()
    print("PASS test_start_fetch_all_refuses_duplicate_job")
    test_cleanup_stale_fetching_resets_pending_chapters()
    print("PASS test_cleanup_stale_fetching_resets_pending_chapters")
    print("\nAll 2 fetch runner tests passed.")
