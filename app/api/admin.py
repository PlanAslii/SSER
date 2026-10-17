"""Administrator settings and security routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_lang, get_theme
from app.core.database import get_db
from app.core.i18n import t
from app.core.security import hash_password, verify_password
from app.models.admin import Administrator

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    settings = request.app.state.settings
    return _templates(request).TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "settings",
            "settings": settings,
            "message": None,
            "error": None,
        },
    )


@router.post("/settings/profile")
async def update_profile(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    display_name: str = Form(""),
    language: str = Form("fa"),
    theme: str = Form("system"),
):
    admin.display_name = display_name.strip() or admin.display_name
    if language in ("fa", "en"):
        admin.language = language
        request.session["language"] = language
    if theme in ("light", "dark", "system"):
        admin.theme = theme
        request.session["theme"] = theme
    db.commit()
    return RedirectResponse("/settings", status_code=302)


@router.post("/settings/password")
async def change_password(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    error = None
    if not verify_password(current_password, admin.password_hash):
        error = "رمز فعلی نادرست است" if lang == "fa" else "Current password is incorrect"
    elif len(new_password) < 8:
        error = "رمز جدید باید حداقل ۸ کاراکتر باشد" if lang == "fa" else "New password must be at least 8 characters"
    elif new_password != confirm_password:
        error = "رمز جدید و تکرار آن یکسان نیستند" if lang == "fa" else "Passwords do not match"
    else:
        admin.password_hash = hash_password(new_password)
        db.commit()
        return RedirectResponse("/settings?ok=1", status_code=302)

    settings = request.app.state.settings
    return _templates(request).TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "settings",
            "settings": settings,
            "message": None,
            "error": error,
        },
        status_code=400,
    )


@router.get("/security", response_class=HTMLResponse)
async def security_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    return _templates(request).TemplateResponse(
        "admin/security.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "security",
        },
    )
