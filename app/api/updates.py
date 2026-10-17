"""Update management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_lang, get_theme
from app.core.database import get_db
from app.core.i18n import t
from app.models.admin import Administrator
from app.services.update_service import UpdateError, UpdateService

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/updates", response_class=HTMLResponse)
async def updates_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    svc = UpdateService(db)
    status = svc.get_update_status()
    history = svc.list_history(limit=20)
    return _templates(request).TemplateResponse(
        "updates/updates.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "updates",
            "update_status": status,
            "history": history,
        },
    )


@router.post("/updates/check")
async def check_updates(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    svc = UpdateService(db)
    try:
        status = svc.get_update_status()
        # force refresh
        svc.fetch_latest_release(force=True)
        status = svc.get_update_status()
        return JSONResponse({"ok": True, "status": status})
    except UpdateError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/updates/install")
async def install_update(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    svc = UpdateService(db)
    try:
        release = svc.fetch_latest_release(force=True)
        if not release:
            return JSONResponse({"ok": False, "error": "No release available"}, status_code=400)
        version = release.get("tag_name", "").lstrip("v")
        history = svc.install_release(version, initiated_by=admin.username, release=release)
        return JSONResponse({
            "ok": True,
            "status": history.status,
            "version": history.new_version,
            "message": "Update installed successfully" if history.status == "successful" else history.failure_reason,
        })
    except UpdateError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.get("/updates/history", response_class=HTMLResponse)
async def update_history_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    page: int = 1,
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    svc = UpdateService(db)
    limit = 25
    offset = (max(1, page) - 1) * limit
    history = svc.list_history(limit=limit, offset=offset)
    return _templates(request).TemplateResponse(
        "updates/history.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "updates",
            "history": history,
            "current_page": page,
        },
    )
