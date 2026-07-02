from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, case, func, not_
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .db import get_session, init_db
from .models import Chapter, ChapterSummary, GlossaryTerm, Novel, StyleGuide
from .services.epub_importer import import_epub_bytes
from .services.epub_exporter import EpubExportError, export_translated_range
from .services.glossary_service import (
    add_term,
    delete_term,
    get_style_guide,
    list_glossary,
    set_style_guide,
)
from .services.provider_settings_service import (
    clear_provider_setting,
    list_provider_settings,
    save_provider_setting,
    set_default_provider_name,
    SUPPORTED_PROVIDERS,
)
from .services.providers.factory import (
    available_providers,
    default_provider,
    get_provider,
    invalidate_cache,
)
from .services.runner import get_last_error, is_translating, start_translation
from .services.glossary_service import translation_quality_status
from .services.fetch_runner import (
    cleanup_stale_fetching,
    is_fetching_novel,
    start_fetch_all,
)
from .services.batch_translation_runner import (
    cleanup_stale_translating,
    eligible_count_for_novel,
    filter_eligible_for_novel,
    get_batch_state,
    is_batch_translating_novel,
    start_batch_translation,
)
from .services.web_service import fetch_chapter_raw, import_web_novel


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Ebook Translator")

settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("APP_SECRET", "dev-secret-change-me"),
    max_age=60 * 60 * 24,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_log_startup = logging.getLogger("app.startup")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        reset = cleanup_stale_fetching()
        if reset:
            _log_startup.info("Reset %d chương fetching do restart", reset)
    except Exception as exc:  # noqa: BLE001
        _log_startup.warning("cleanup_stale_fetching thất bại: %s", exc)
    try:
        reset = cleanup_stale_translating()
        if reset:
            _log_startup.info("Reset %d chương translating do restart", reset)
    except Exception as exc:  # noqa: BLE001
        _log_startup.warning("cleanup_stale_translating thất bại: %s", exc)


def _consume_flash(request: Request) -> Optional[dict]:
    flashes = request.session.pop("_flash", None)
    if not flashes:
        return None
    return flashes[-1]


def _set_flash(request: Request, message: str, type_: str = "info") -> None:
    request.session.setdefault("_flash", []).append({"message": message, "type": type_})


_STATUS_LABELS = {
    "translating": "Đang dịch",
    "fetching": "Đang tải",
    "translated": "Đã dịch xong",
    "fetched": "Đã tải",
    "error": "Có lỗi",
    "pending": "Mới import",
}


_DETAIL_STATUS_MAP = {
    "translating": "translating",
    "fetching": "fetching",
    "error": "error",
    "translated": "translated",
}


def _chapter_detail_status(chapter: Chapter) -> str:
    """Derive a UI display status from chapter fields.

    Priority order ensures active/error states are not hidden by stale fields.
    """
    raw = getattr(chapter, "raw_text", None)
    translated = getattr(chapter, "translated_text", None)
    status = getattr(chapter, "status", "") or ""
    if status in ("translating",):
        return "translating"
    if status in ("fetching",):
        return "fetching"
    if status == "error":
        return "error"
    if translated:
        return "translated"
    if status == "translated":
        return "translated"
    if raw:
        return "fetched"
    return "not_fetched"


def _display_status_from_row(row: dict) -> str:
    """Same priority order as `_chapter_detail_status` but works on lightweight row dicts."""
    has_raw = bool(row.get("has_raw"))
    has_translated = bool(row.get("has_translated"))
    status = row.get("status", "") or ""
    if status == "translating":
        return "translating"
    if status == "fetching":
        return "fetching"
    if status == "error":
        return "error"
    if has_translated:
        return "translated"
    if status == "translated":
        return "translated"
    if has_raw:
        return "fetched"
    return "not_fetched"


def _batch_display_status(row: dict, batch_state: Optional[dict]) -> str:
    """Overlay in-memory batch progress on the persisted chapter status."""
    display_status = _display_status_from_row(row)
    if not batch_state or display_status == "translated":
        return display_status
    chapter_id = row.get("id")
    if chapter_id == batch_state.get("current_chapter_id"):
        return "translating"
    if chapter_id in set(batch_state.get("queued_chapter_ids") or []):
        return "queue"
    return display_status


def _query_novel_chapter_rows(session: Session, novel_id: int) -> list[dict]:
    """Query chapters without loading raw_text or translated_text content.

    Returns lightweight row dicts sized for novel detail listing and stats
    calculation. Mass-text columns stay on disk to avoid loading megabytes of
    text per 1000+ chapter novel.
    """
    has_raw_col = Chapter.raw_text.isnot(None).label("has_raw")
    has_translated_col = Chapter.translated_text.isnot(None).label("has_translated")
    rows = session.exec(
        select(
            Chapter.id,
            Chapter.novel_id,
            Chapter.index,
            Chapter.title,
            Chapter.translated_title,
            Chapter.source_url,
            Chapter.status,
            has_raw_col,
            has_translated_col,
        )
        .where(Chapter.novel_id == novel_id)
        .order_by(Chapter.index)
    ).all()
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "novel_id": r.novel_id,
                "index": r.index,
                "title": r.title,
                "translated_title": r.translated_title,
                "source_url": r.source_url,
                "status": r.status or "",
                "has_raw": bool(r.has_raw),
                "has_translated": bool(r.has_translated),
            }
        )
    return out


def _chapter_row_from_chapter(chapter: Chapter) -> dict:
    """Build a lightweight row dict from a full Chapter ORM object.

    Used by single-chapter refresh paths (e.g. `/chapters/{id}/row`) so the
    partial template can be rendered without exposing the full text fields.
    """
    quality: Optional[str] = None
    translated_text = getattr(chapter, "translated_text", None)
    raw_text = getattr(chapter, "raw_text", None)
    if translated_text:
        quality = translation_quality_status(translated_text, raw_text)
    return {
        "id": chapter.id,
        "novel_id": chapter.novel_id,
        "index": chapter.index,
        "title": chapter.title,
        "translated_title": chapter.translated_title,
        "source_url": chapter.source_url,
        "status": getattr(chapter, "status", "") or "",
        "has_raw": bool(getattr(chapter, "raw_text", None)),
        "has_translated": bool(getattr(chapter, "translated_text", None)),
        "quality": quality,
    }


def _novel_stats_from_rows(rows: list[dict]) -> dict:
    """Compute novel stats from lightweight row dicts (no text loaded)."""
    translated = 0
    translating = 0
    fetching = 0
    error = 0
    raw = 0
    not_fetched = 0
    for row in rows:
        d = _display_status_from_row(row)
        if d == "translated":
            translated += 1
        elif d == "translating":
            translating += 1
        elif d == "fetching":
            fetching += 1
            raw += 1
        elif d == "fetched":
            raw += 1
        elif d == "error":
            error += 1
        elif d == "not_fetched":
            not_fetched += 1
    return {
        "total": len(rows),
        "raw": raw,
        "translated": translated,
        "translating": translating,
        "fetching": fetching,
        "error": error,
        "not_fetched": not_fetched,
        "active_error": translating + fetching + error,
    }


def _novel_poll_active(
    stats: dict,
    *,
    fetch_running: bool = False,
    batch_state: Optional[dict] = None,
) -> bool:
    """Whether the novel detail page still needs background refreshes."""
    return bool(
        fetch_running
        or batch_state is not None
        or stats.get("translating", 0)
        or stats.get("fetching", 0)
    )


def _novel_stats_aggregate(session: Session, novel_id: int) -> dict:
    """Compute novel stats via SQL aggregates without loading chapter text."""
    has_raw = Chapter.raw_text.isnot(None)
    has_translated = Chapter.translated_text.isnot(None)
    not_raw = not_(has_raw)
    not_translated = not_(has_translated)
    active_statuses = ["translating", "fetching", "error", "translated"]

    def status_eq(value: str):
        return Chapter.status == value

    translated_count = func.sum(case((has_translated, 1), else_=0))
    translating_count = func.sum(
        case((and_(not_translated, status_eq("translating")), 1), else_=0)
    )
    fetching_count = func.sum(
        case((and_(not_translated, status_eq("fetching")), 1), else_=0)
    )
    error_count = func.sum(
        case((and_(not_translated, status_eq("error")), 1), else_=0)
    )
    translated_status_count = func.sum(
        case((and_(not_translated, status_eq("translated")), 1), else_=0)
    )
    not_active = Chapter.status.notin_(active_statuses)
    fetched_count = func.sum(
        case((and_(has_raw, not_translated, not_active), 1), else_=0)
    )
    not_fetched_count = func.sum(
        case((and_(not_raw, not_translated, not_active), 1), else_=0)
    )
    stmt = select(
        func.count(Chapter.id).label("total"),
        translated_count.label("translated"),
        translating_count.label("translating"),
        fetching_count.label("fetching"),
        error_count.label("error"),
        translated_status_count.label("translated_status"),
        fetched_count.label("fetched"),
        not_fetched_count.label("not_fetched"),
    ).where(Chapter.novel_id == novel_id)
    row = session.exec(stmt).one()
    translated = (row.translated or 0) + (row.translated_status or 0)
    translating = row.translating or 0
    fetching = row.fetching or 0
    error = row.error or 0
    raw = (fetching or 0) + (row.fetched or 0)
    not_fetched = row.not_fetched or 0
    return {
        "total": row.total or 0,
        "raw": raw,
        "translated": translated,
        "translating": translating,
        "fetching": fetching,
        "error": error,
        "not_fetched": not_fetched,
        "active_error": translating + fetching + error,
    }


def _novel_stats_from_chapters(chapters: list[Chapter]) -> dict:
    total = len(chapters)
    raw = 0
    translated = 0
    translating = 0
    fetching = 0
    error = 0
    not_fetched = 0
    for c in chapters:
        d = _chapter_detail_status(c)
        if d == "translated":
            translated += 1
        elif d == "translating":
            translating += 1
        elif d == "fetching":
            fetching += 1
            raw += 1
        elif d == "fetched":
            raw += 1
        elif d == "error":
            error += 1
        elif d == "not_fetched":
            not_fetched += 1
    active_error = translating + fetching + error
    return {
        "total": total,
        "raw": raw,
        "translated": translated,
        "translating": translating,
        "fetching": fetching,
        "error": error,
        "not_fetched": not_fetched,
        "active_error": active_error,
    }


def _safe_return_to(value: Optional[str], novel_id: int, chapter_id: Optional[int]) -> str:
    """Validate an internal redirect path; return a safe fallback if invalid."""
    if not value:
        return f"/novels/{novel_id}"
    if not isinstance(value, str):
        return f"/novels/{novel_id}"
    v = value.strip()
    if not v.startswith("/") or v.startswith("//"):
        return f"/novels/{novel_id}"
    allowed_prefixes = [f"/novels/{novel_id}"]
    if chapter_id is not None:
        allowed_prefixes.append(f"/chapters/{chapter_id}")
    if not any(v == p or v.startswith(p + "/") or v.startswith(p + "?") or v.startswith(p + "#") for p in allowed_prefixes):
        return f"/novels/{novel_id}"
    return v


def _row_partial(chapter: Chapter, novel: Novel):
    return {
        "novel": novel,
        "chapter": chapter,
        "display_status": _chapter_detail_status(chapter),
    }


def _stats_partial(chapters: list[Chapter], novel: Novel, novel_stats: Optional[dict] = None):
    return {
        "novel": novel,
        "stats": novel_stats or _novel_stats_from_chapters(chapters),
    }


def _chapter_row_response(
    novel: Novel,
    chapter: Chapter,
    session: Session,
    status_code: int = 200,
    trigger_event: Optional[str] = None,
    include_stats: bool = True,
):
    """Render a chapter row fragment wrapped in a `<table><tbody>` so HTMX can
    parse the `<tr>` in a table context, plus an optional out-of-band stats
    update. With the row marked `hx-swap-oob="outerHTML"`, HTMX swaps it by id
    without having to do a target outerHTML parse of a bare `<tr>`.
    """
    session.refresh(chapter)
    chapter_row = _chapter_row_from_chapter(chapter)
    display_status = _batch_display_status(chapter_row, get_batch_state(novel.id))
    novel_stats = _novel_stats_aggregate(session, novel.id)
    quality: Optional[str] = None
    translated_text = getattr(chapter, "translated_text", None)
    raw_text = getattr(chapter, "raw_text", None)
    if translated_text:
        quality = translation_quality_status(translated_text, raw_text)
    chapter_row["quality"] = quality
    row_html = templates.get_template("partials/novel_chapter_row.html").render(
        novel=novel, chapter=chapter_row, display_status=display_status,
    )
    stats_html = ""
    if include_stats:
        stats_html = templates.get_template("partials/novel_stats.html").render(
            novel=novel, stats=novel_stats, oob=True,
        )
    from fastapi.responses import Response
    body = "<table><tbody>" + row_html + "</tbody></table>" + stats_html
    headers = {}
    if trigger_event:
        headers["HX-Trigger"] = json.dumps({trigger_event: {"chapterId": chapter.id, "novelId": novel.id}})
    return Response(
        content=body,
        media_type="text/html",
        status_code=status_code,
        headers=headers or None,
    )


def _compute_novel_status(chapters: list[Chapter]) -> str:
    """Derive a single status label for the homepage card from the chapter list."""
    if not chapters:
        return "pending"
    statuses = {c.status for c in chapters}
    return _novel_status_from_status_set(statuses)


def _novel_status_from_status_set(statuses: set) -> str:
    """Same priority logic as `_compute_novel_status` but takes a status set directly."""
    if not statuses:
        return "pending"
    statuses = {s for s in statuses if s}
    if statuses & {"translating", "fetching"}:
        return "translating"
    if "error" in statuses:
        return "error"
    if "translated" in statuses and statuses.issubset({"translated"}):
        return "translated"
    if "fetched" in statuses and statuses.issubset({"fetched", "translated"}):
        return "fetched"
    return "pending"


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    novels = list(session.exec(select(Novel).order_by(Novel.id.desc())).all())
    chapter_counts: dict[int, int] = {}
    novel_statuses: dict[int, str] = {}
    for n in novels:
        statuses_rows = session.exec(
            select(Chapter.status).where(Chapter.novel_id == n.id)
        ).all()
        statuses = set(statuses_rows)
        chapter_counts[n.id] = len(statuses_rows)
        novel_statuses[n.id] = _novel_status_from_status_set(statuses)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "novels": novels,
            "chapter_counts": chapter_counts,
            "novel_statuses": novel_statuses,
            "status_labels": _STATUS_LABELS,
            "has_provider": bool(available_providers(session)),
            "has_default": bool(default_provider(session)),
            "active_nav": "home",
            "flash": _consume_flash(request),
        },
    )


@app.post("/novels/import-url")
async def import_url(request: Request, url: str = Form(...), session: Session = Depends(get_session)):
    try:
        novel = import_web_novel(session, url)
    except Exception as e:
        _set_flash(request, f"Lỗi import URL: {e}", "error")
        return RedirectResponse(url="/", status_code=303)
    if bool(getattr(settings, "auto_fetch_after_import", True)):
        started = start_fetch_all(novel.id)
        if started:
            _set_flash(request, "Đang tải toàn bộ nội dung chương ở chế độ nền.", "info")
    return RedirectResponse(url=f"/novels/{novel.id}", status_code=303)


@app.post("/novels/import-epub")
async def import_epub(request: Request, epub: UploadFile = File(...), session: Session = Depends(get_session)):
    content = await epub.read()
    if not content:
        _set_flash(request, "File rỗng", "error")
        return RedirectResponse(url="/", status_code=303)
    try:
        novel = import_epub_bytes(session, content, original_filename=epub.filename)
    except Exception as e:
        _set_flash(request, f"Lỗi import EPUB: {e}", "error")
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url=f"/novels/{novel.id}", status_code=303)


@app.post("/novels/{novel_id}/delete")
def delete_novel(novel_id: int, session: Session = Depends(get_session)):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    session.exec(select(ChapterSummary).where(ChapterSummary.novel_id == novel_id))
    for model in (Chapter, GlossaryTerm, ChapterSummary, StyleGuide):
        rows = list(session.exec(select(model).where(model.novel_id == novel_id)).all())
        for r in rows:
            session.delete(r)
    session.delete(novel)
    session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/novels/{novel_id}", response_class=HTMLResponse)
def novel_detail(
    request: Request,
    novel_id: int,
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    chapter_rows_data = _query_novel_chapter_rows(session, novel_id)
    glossary = list_glossary(session, novel_id)
    style_guide = get_style_guide(session, novel_id)
    batch_state = get_batch_state(novel.id)
    chapter_rows = [
        {
            "chapter": row,
            "novel": novel,
            "display_status": _batch_display_status(row, batch_state),
        }
        for row in chapter_rows_data
    ]
    stats = _novel_stats_from_rows(chapter_rows_data)
    fetch_running = is_fetching_novel(novel.id)
    pending_count = stats.get("not_fetched", 0) + stats.get("error", 0)
    batch_translate_running = batch_state is not None
    poll_active = _novel_poll_active(
        stats,
        fetch_running=fetch_running,
        batch_state=batch_state,
    )
    eligible_translate_count = eligible_count_for_novel(novel.id)
    return templates.TemplateResponse(
        request,
        "novel.html",
        {
            "novel": novel,
            "chapters": chapter_rows_data,
            "chapter_rows": chapter_rows,
            "glossary": glossary,
            "style_guide": style_guide,
            "novel_stats": stats,
            "fetch_running": fetch_running,
            "pending_count": pending_count,
            "batch_translate_running": batch_translate_running,
            "poll_active": poll_active,
            "eligible_translate_count": eligible_translate_count,
            "active_nav": "home",
            "flash": _consume_flash(request),
        },
    )


@app.get("/novels/{novel_id}/chapters/{chapter_id}/row", response_class=HTMLResponse)
def novel_chapter_row(
    novel_id: int,
    chapter_id: int,
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    chapter = session.get(Chapter, chapter_id)
    if novel is None or chapter is None or chapter.novel_id != novel.id:
        raise HTTPException(404)
    return _chapter_row_response(novel, chapter, session)


@app.get("/novels/{novel_id}/chapters", response_class=HTMLResponse)
def novel_chapters_partial(
    request: Request,
    novel_id: int,
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404)
    chapter_rows_data = _query_novel_chapter_rows(session, novel_id)
    batch_state = get_batch_state(novel.id)
    rows_html = "".join(
        templates.get_template("partials/novel_chapter_row.html").render(
            novel=novel,
            chapter=row,
            display_status=_batch_display_status(row, batch_state),
        )
        for row in chapter_rows_data
    )
    novel_stats = _novel_stats_from_rows(chapter_rows_data)
    poll_active = _novel_poll_active(
        novel_stats,
        fetch_running=is_fetching_novel(novel.id),
        batch_state=batch_state,
    )
    stats_html = templates.get_template("partials/novel_stats.html").render(
        novel=novel,
        stats=novel_stats,
        oob=True,
    )
    return HTMLResponse(
        content=rows_html + stats_html,
        headers={"X-Novel-Poll-Active": "1" if poll_active else "0"},
    )


@app.get("/novels/{novel_id}/stats", response_class=HTMLResponse)
def novel_stats_partial(
    request: Request,
    novel_id: int,
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404)
    novel_stats = _novel_stats_aggregate(session, novel_id)
    return templates.TemplateResponse(
        request,
        "partials/novel_stats.html",
        {"novel": novel, "stats": novel_stats},
    )


@app.get("/novels/{novel_id}/export.epub")
def export_novel_epub(
    request: Request,
    novel_id: int,
    from_index: int,
    to_index: int,
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    try:
        result = export_translated_range(session, novel, from_index, to_index)
    except EpubExportError as exc:
        _set_flash(request, f"Không thể xuất EPUB: {exc}", "error")
        return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

    quoted_filename = quote(result.filename)
    return Response(
        content=result.content,
        media_type="application/epub+zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{result.filename}\"; filename*=UTF-8''{quoted_filename}"
            ),
        },
    )


@app.post("/novels/{novel_id}/style")
def update_style(
    novel_id: int,
    style_guide: str = Form(...),
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404)
    set_style_guide(session, novel_id, style_guide)
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)


@app.post("/novels/{novel_id}/glossary")
def add_glossary_term(
    novel_id: int,
    source: str = Form(...),
    target: str = Form(...),
    category: str = Form("general"),
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404)
    if source.strip() and target.strip():
        add_term(session, novel_id, source, target, category=category)
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)


@app.post("/novels/{novel_id}/glossary/{term_id}/delete")
def delete_glossary_term(novel_id: int, term_id: int, session: Session = Depends(get_session)):
    delete_term(session, term_id)
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)


@app.post("/novels/{novel_id}/fetch-all")
def fetch_all(novel_id: int, request: Request, session: Session = Depends(get_session)):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")
    if is_fetching_novel(novel_id):
        _set_flash(request, "Đang tải nội dung rồi, vui lòng đợi.", "info")
        return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)
    if not start_fetch_all(novel_id):
        _set_flash(request, "Không thể khởi động job tải.", "error")
    else:
        _set_flash(request, "Đang tải nội dung các chương còn thiếu ở chế độ nền.", "info")
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)


@app.post("/novels/{novel_id}/translate-selected")
async def translate_selected(
    novel_id: int,
    request: Request,
    chapter_ids: list[int] = Form(default=[]),
    session: Session = Depends(get_session),
):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404, "Không tìm thấy truyện")

    is_htmx = (request.headers.get("HX-Request") or "").lower() == "true"

    def finish(message: str, type_: str = "info", *, refresh: bool = False):
        if is_htmx:
            if refresh:
                return novel_chapters_partial(request, novel_id, session)
            return Response(
                status_code=204,
                headers={
                    "HX-Trigger": json.dumps(
                        {"novel-batch-notice": {"message": message, "type": type_}}
                    )
                },
            )
        _set_flash(request, message, type_)
        return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)

    provider_name = default_provider(session)
    if not provider_name:
        return finish(
            "Chưa có provider mặc định. Mở Cấu hình API và bấm \"Đặt làm mặc định\" cho một provider đã cấu hình.",
            "error",
        )

    if not chapter_ids:
        return finish("Chưa chọn chương nào để dịch.")

    if is_batch_translating_novel(novel_id):
        return finish("Đang có hàng đợi dịch cho truyện này, vui lòng đợi.")

    eligible_ids = filter_eligible_for_novel(novel_id, chapter_ids)
    if not eligible_ids:
        return finish(
            "Không có chương nào đủ điều kiện dịch (cần đã có nội dung gốc và chưa có bản dịch).",
        )

    started, count = start_batch_translation(novel_id, eligible_ids, provider_name)
    if not started:
        return finish("Không thể khởi động job dịch. Vui lòng thử lại.", "error")
    return finish(
        f"Đang dịch {count} chương đã chọn ở chế độ nền (provider {provider_name}).",
        refresh=True,
    )


@app.get("/chapters/{chapter_id}", response_class=HTMLResponse)
def chapter_view(
    request: Request,
    chapter_id: int,
    view: str = "vi",
    session: Session = Depends(get_session),
):
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404)
    novel = session.get(Novel, chapter.novel_id)
    chapters = list(session.exec(select(Chapter).where(Chapter.novel_id == chapter.novel_id).order_by(Chapter.index)).all())
    prev_id = next_id = None
    for i, c in enumerate(chapters):
        if c.id == chapter_id:
            if i > 0:
                prev_id = chapters[i - 1].id
            if i < len(chapters) - 1:
                next_id = chapters[i + 1].id
            break
    providers = available_providers(session) or []
    from .services import translation_jobs as jobs
    job = jobs.get(session, chapter_id)
    chapter_items = [
        {"chapter": item, "display_status": _chapter_detail_status(item)}
        for item in chapters
    ]
    translation_quality = translation_quality_status(
        getattr(chapter, "translated_text", None),
        getattr(chapter, "raw_text", None),
    )
    translation_quality_for_items = {
        item["chapter"].id: translation_quality_status(
            getattr(item["chapter"], "translated_text", None),
            getattr(item["chapter"], "raw_text", None),
        )
        for item in chapter_items
    }
    return templates.TemplateResponse(
        request,
        "chapter.html",
        {
            "novel": novel,
            "chapter": chapter,
            "prev_id": prev_id,
            "next_id": next_id,
            "view": view,
            "display_status": _chapter_detail_status(chapter),
            "translation_quality": translation_quality,
            "chapter_items": chapter_items,
            "chapter_quality_by_id": translation_quality_for_items,
            "providers": providers,
            "default_provider": default_provider(session),
            "has_provider": bool(providers),
            "job": job,
            "active_nav": "home",
            "flash": _consume_flash(request),
        },
    )


def _stats_only_response(novel: Novel, chapter: Chapter, session: Session, trigger_event: Optional[str] = None):
    """Return a no-swap HTMX response that only emits a refresh event.

    The novel detail page has independent HTMX regions for the chapter table
    and stats. POST actions should not return OOB fragments here because those
    can race with the table/stats refreshes triggered by the same response and
    cause htmx swap errors in 1.9.10. The event lets each region fetch itself
    with a normal GET in its own DOM context.
    """
    from fastapi.responses import Response
    headers = {}
    if trigger_event:
        headers["HX-Trigger"] = json.dumps({trigger_event: {"chapterId": chapter.id, "novelId": novel.id}})
    return Response(
        content="",
        media_type="text/html",
        status_code=200,
        headers=headers or None,
    )


@app.post("/chapters/{chapter_id}/fetch")
def chapter_fetch(
    chapter_id: int,
    request: Request,
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404)
    novel = session.get(Novel, chapter.novel_id)
    if novel is None:
        raise HTTPException(404)
    is_htmx = (request.headers.get("HX-Request") or "").lower() == "true"
    safe_return = _safe_return_to(return_to, novel.id, chapter_id)
    detail_call = safe_return.startswith(f"/novels/{novel.id}")
    trigger_event = "novel-chapters-refresh"
    try:
        fetch_chapter_raw(session, chapter)
    except Exception as e:
        _set_flash(request, f"Lỗi fetch: {e}", "error")
        if detail_call:
            chapter = session.get(Chapter, chapter_id)
            return _stats_only_response(novel, chapter, session, trigger_event=trigger_event)
        return RedirectResponse(url=safe_return, status_code=303)
    if detail_call:
        chapter = session.get(Chapter, chapter_id)
        return _stats_only_response(novel, chapter, session, trigger_event=trigger_event)
    if is_htmx:
        from fastapi.responses import Response
        return Response(content="", media_type="text/html", status_code=200)
    return RedirectResponse(url=f"/chapters/{chapter_id}?view=raw", status_code=303)


@app.post("/chapters/{chapter_id}/translate")
def chapter_translate(
    chapter_id: int,
    request: Request,
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404)
    novel = session.get(Novel, chapter.novel_id)
    if novel is None:
        raise HTTPException(404)
    safe_return = _safe_return_to(return_to, novel.id, chapter_id)
    detail_call = safe_return.startswith(f"/novels/{novel.id}")
    if not chapter.raw_text:
        _set_flash(request, "Chương chưa có nội dung gốc. Hãy fetch trước khi dịch.", "error")
        return _detail_or_default_redirect(detail_call, safe_return, chapter_id, novel, chapter, session)
    if is_translating(chapter_id):
        _set_flash(request, "Chương này đang được dịch, vui lòng đợi.", "error")
        return _detail_or_default_redirect(detail_call, safe_return, chapter_id, novel, chapter, session)

    provider_name = default_provider(session)
    if not provider_name:
        _set_flash(
            request,
            "Chưa có provider mặc định. Mở Cấu hình API và bấm \"Đặt làm mặc định\" cho một provider đã cấu hình.",
            "error",
        )
        return _detail_or_default_redirect(detail_call, safe_return, chapter_id, novel, chapter, session)

    pending_error = get_last_error(chapter_id)
    previous_translated = chapter.translated_text or ""
    previous_quality = translation_quality_status(previous_translated, chapter.raw_text)
    if previous_translated and previous_quality == "bad":
        chapter.translation_warning = None
    chapter.status = "translating"
    chapter.error_message = None
    chapter.translation_provider = provider_name
    session.add(chapter)
    session.commit()

    started = start_translation(novel.id, chapter_id, provider_name)
    if not started:
        _set_flash(request, "Chương này đang được dịch, vui lòng đợi.", "error")

    flash_msg = f"Đang dịch ở nền bằng provider {provider_name}. Trang sẽ tự cập nhật khi xong."
    if pending_error:
        flash_msg = f"Đang dịch lại ở nền bằng {provider_name} (lỗi trước: {pending_error})."
    _set_flash(request, flash_msg)
    if detail_call:
        chapter = session.get(Chapter, chapter_id)
        return _stats_only_response(
            novel, chapter, session,
            trigger_event="novel-chapters-refresh",
        )
    return RedirectResponse(url=f"/chapters/{chapter_id}?view=vi", status_code=303)


def _detail_or_default_redirect(detail_call: bool, safe_return: str, chapter_id: int, novel, chapter, session):
    if detail_call:
        chapter = session.get(Chapter, chapter_id)
        return _stats_only_response(
            novel, chapter, session,
            trigger_event="novel-chapters-refresh",
        )
    return RedirectResponse(url=f"/chapters/{chapter_id}", status_code=303)


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)


@app.get("/settings/api", response_class=HTMLResponse)
def api_settings_view(request: Request, session: Session = Depends(get_session)):
    settings_list = list_provider_settings(session)
    avail = available_providers(session)
    return templates.TemplateResponse(
        request,
        "api_settings.html",
        {
            "settings_list": settings_list,
            "default_provider": default_provider(session),
            "has_provider": bool(avail),
            "has_default": bool(default_provider(session)),
            "active_nav": "settings",
            "flash": _consume_flash(request),
        },
    )


@app.post("/settings/api/{provider}/set-default")
def api_settings_set_default(provider: str, request: Request, session: Session = Depends(get_session)):
    name = (provider or "").lower()
    if name not in SUPPORTED_PROVIDERS:
        _set_flash(request, f"Provider không hỗ trợ: {name}", "error")
        return RedirectResponse(url="/settings/api", status_code=303)
    cfg = list_provider_settings(session)
    cfg_map = {c["provider"]: c for c in cfg}
    info = cfg_map.get(name)
    if info is None or not info.get("has_key"):
        _set_flash(
            request,
            f"Chưa cấu hình API key cho {name}. Hãy nhập key trước khi đặt làm mặc định.",
            "error",
        )
        return RedirectResponse(url="/settings/api", status_code=303)
    set_default_provider_name(session, name)
    invalidate_cache(name)
    _set_flash(request, f"Đã đặt {name} làm provider mặc định.", "success")
    return RedirectResponse(url="/settings/api", status_code=303)


@app.post("/settings/api/{provider}/save")
def api_settings_save(
    provider: str,
    request: Request,
    api_key: str = Form(""),
    base_url: str = Form(""),
    model: str = Form(""),
    group_id: str = Form(""),
    session: Session = Depends(get_session),
):
    name = (provider or "").lower()
    try:
        save_provider_setting(
            session,
            name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            group_id=group_id,
        )
    except ValueError as e:
        _set_flash(request, str(e), "error")
        return RedirectResponse(url="/settings/api", status_code=303)
    invalidate_cache(name)
    _set_flash(request, f"Đã lưu cấu hình cho {name}.", "success")
    return RedirectResponse(url="/settings/api", status_code=303)


@app.post("/settings/api/{provider}/clear")
def api_settings_clear(provider: str, request: Request, session: Session = Depends(get_session)):
    name = (provider or "").lower()
    clear_provider_setting(session, name)
    invalidate_cache(name)
    _set_flash(request, f"Đã xóa cấu hình {name} trong DB. App sẽ dùng lại giá trị trong .env (nếu có).", "info")
    return RedirectResponse(url="/settings/api", status_code=303)


@app.post("/settings/api/{provider}/test")
def api_settings_test(provider: str, request: Request, session: Session = Depends(get_session)):
    name = (provider or "").lower()
    try:
        provider_obj = get_provider(session, name)
    except Exception as e:
        _set_flash(request, f"Không thể khởi tạo provider {name}: {e}", "error")
        return RedirectResponse(url="/settings/api", status_code=303)
    try:
        result = provider_obj.ping()
    except Exception as e:  # noqa: BLE001
        _set_flash(request, f"Kiểm tra kết nối {name} thất bại: {e}", "error")
        return RedirectResponse(url="/settings/api", status_code=303)
    if result.get("ok"):
        reply = result.get("reply", "")
        _set_flash(
            request,
            f"Kết nối {name} thành công. Model={result.get('model')} · Phản hồi={reply[:16]!r}",
            "success",
        )
    else:
        _set_flash(request, f"Kiểm tra kết nối {name} thất bại: {result.get('error')}", "error")
    return RedirectResponse(url="/settings/api", status_code=303)


if __name__ == "__main__":  # pragma: no cover
    main()
