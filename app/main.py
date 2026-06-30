from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .db import get_session, init_db
from .models import Chapter, ChapterSummary, GlossaryTerm, Novel, StyleGuide
from .services.epub_importer import import_epub_bytes
from .services.glossary_service import (
    add_term,
    delete_term,
    get_style_guide,
    list_glossary,
    set_style_guide,
)
from .services.providers.factory import available_providers, default_provider
from .services.runner import get_last_error, is_translating, start_translation
from .services.web_service import fetch_chapter_raw, import_web_novel


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Ebook Translator")

settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("APP_SECRET", "dev-secret-change-me"),
    max_age=60 * 60 * 24,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _consume_flash(request: Request) -> Optional[dict]:
    flashes = request.session.pop("_flash", None)
    if not flashes:
        return None
    return flashes[-1]


def _set_flash(request: Request, message: str, type_: str = "info") -> None:
    request.session.setdefault("_flash", []).append({"message": message, "type": type_})


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    novels = list(session.exec(select(Novel).order_by(Novel.id.desc())).all())
    chapter_counts: dict[int, int] = {}
    for n in novels:
        chapter_counts[n.id] = len(
            list(session.exec(select(Chapter).where(Chapter.novel_id == n.id)).all())
        )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "novels": novels,
            "chapter_counts": chapter_counts,
            "has_provider": bool(available_providers()),
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
    chapters = list(session.exec(select(Chapter).where(Chapter.novel_id == novel_id).order_by(Chapter.index)).all())
    glossary = list_glossary(session, novel_id)
    style_guide = get_style_guide(session, novel_id)
    return templates.TemplateResponse(
        request,
        "novel.html",
        {
            "novel": novel,
            "chapters": chapters,
            "glossary": glossary,
            "style_guide": style_guide,
            "flash": _consume_flash(request),
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
def fetch_all(novel_id: int, session: Session = Depends(get_session)):
    novel = session.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(404)
    chapters = list(session.exec(select(Chapter).where(Chapter.novel_id == novel_id).order_by(Chapter.index)).all())
    for ch in chapters:
        if ch.source_url and not ch.raw_text:
            try:
                fetch_chapter_raw(session, ch)
            except Exception:
                pass
    return RedirectResponse(url=f"/novels/{novel_id}", status_code=303)


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
    providers = available_providers() or []
    return templates.TemplateResponse(
        request,
        "chapter.html",
        {
            "novel": novel,
            "chapter": chapter,
            "prev_id": prev_id,
            "next_id": next_id,
            "view": view,
            "providers": providers,
            "default_provider": default_provider(),
            "has_provider": bool(providers),
            "flash": _consume_flash(request),
        },
    )


@app.post("/chapters/{chapter_id}/fetch")
def chapter_fetch(chapter_id: int, request: Request, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404)
    try:
        fetch_chapter_raw(session, chapter)
    except Exception as e:
        _set_flash(request, f"Lỗi fetch: {e}", "error")
        return RedirectResponse(url=f"/chapters/{chapter_id}", status_code=303)
    return RedirectResponse(url=f"/chapters/{chapter_id}", status_code=303)


@app.post("/chapters/{chapter_id}/translate")
def chapter_translate(
    chapter_id: int,
    request: Request,
    provider: str = Form("minimax"),
    session: Session = Depends(get_session),
):
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404)
    novel = session.get(Novel, chapter.novel_id)
    if novel is None:
        raise HTTPException(404)
    if not chapter.raw_text:
        _set_flash(request, "Chương chưa có nội dung gốc. Hãy fetch trước khi dịch.", "error")
        return RedirectResponse(url=f"/chapters/{chapter_id}", status_code=303)
    if is_translating(chapter_id):
        _set_flash(request, "Chương này đang được dịch, vui lòng đợi.", "error")
        return RedirectResponse(url=f"/chapters/{chapter_id}", status_code=303)

    pending_error = get_last_error(chapter_id)
    chapter.status = "translating"
    chapter.translation_provider = provider
    session.add(chapter)
    session.commit()

    started = start_translation(novel.id, chapter_id, provider)
    if not started:
        _set_flash(request, "Chương này đang được dịch, vui lòng đợi.", "error")

    flash_msg = "Đang dịch ở nền. Trang sẽ tự cập nhật khi xong."
    if pending_error:
        flash_msg = f"Đang dịch lại ở nền (lỗi trước: {pending_error})."
    _set_flash(request, flash_msg)
    return RedirectResponse(url=f"/chapters/{chapter_id}?view=vi", status_code=303)


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
