"""Authentication and first-run setup routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.i18n import t
from app.core.security import hash_password, verify_password
from app.models.admin import Administrator

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    if request.session.get("admin_id"):
        return RedirectResponse("/dashboard", status_code=302)
    admin_count = db.query(Administrator).count()
    if admin_count == 0:
        return RedirectResponse("/setup", status_code=302)
    lang = request.session.get("language", "fa")
    return _templates(request).TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "error": None,
            "t": lambda k: t(k, lang),
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    lang = request.session.get("language", "fa")
    admin = db.query(Administrator).filter(Administrator.username == username).first()
    error = None
    if not admin or not admin.is_active:
        error = "نام کاربری یا رمز عبور نامعتبر است" if lang == "fa" else "Invalid username or password"
    elif admin.locked_until and admin.locked_until > datetime.now(timezone.utc):
        error = "حساب موقتاً قفل شده است" if lang == "fa" else "Account temporarily locked"
    elif not verify_password(password, admin.password_hash):
        admin.failed_login_count = (admin.failed_login_count or 0) + 1
        if admin.failed_login_count >= 5:
            from datetime import timedelta
            admin.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()
        error = "نام کاربری یا رمز عبور نامعتبر است" if lang == "fa" else "Invalid username or password"
    else:
        admin.failed_login_count = 0
        admin.locked_until = None
        admin.last_login_at = datetime.now(timezone.utc)
        admin.last_login_ip = request.client.host if request.client else None
        db.commit()
        request.session["admin_id"] = admin.id
        request.session["language"] = admin.language or "fa"
        request.session["theme"] = admin.theme or "system"
        return RedirectResponse("/dashboard", status_code=302)

    return _templates(request).TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "error": error,
            "t": lambda k: t(k, lang),
        },
        status_code=400,
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: Session = Depends(get_db)):
    if db.query(Administrator).count() > 0:
        return RedirectResponse("/login", status_code=302)
    lang = request.session.get("language", "fa")
    return _templates(request).TemplateResponse(
        "auth/setup.html",
        {
            "request": request,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "error": None,
            "t": lambda k: t(k, lang),
        },
    )


@router.post("/setup", response_class=HTMLResponse)
async def setup_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    display_name: str = Form(""),
    db: Session = Depends(get_db),
):
    lang = request.session.get("language", "fa")
    if db.query(Administrator).count() > 0:
        return RedirectResponse("/login", status_code=302)
    error = None
    if len(username) < 3:
        error = "نام کاربری باید حداقل ۳ کاراکتر باشد" if lang == "fa" else "Username must be at least 3 characters"
    elif len(password) < 8:
        error = "رمز عبور باید حداقل ۸ کاراکتر باشد" if lang == "fa" else "Password must be at least 8 characters"
    elif password != password_confirm:
        error = "رمز عبور و تکرار آن یکسان نیستند" if lang == "fa" else "Passwords do not match"
    else:
        admin = Administrator(
            username=username.strip(),
            password_hash=hash_password(password),
            display_name=display_name.strip() or username,
            is_active=True,
            is_superadmin=True,
            language=lang,
        )
        db.add(admin)
        db.commit()
        request.session["admin_id"] = admin.id
        return RedirectResponse("/dashboard", status_code=302)

    return _templates(request).TemplateResponse(
        "auth/setup.html",
        {
            "request": request,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "error": error,
            "t": lambda k: t(k, lang),
        },
        status_code=400,
    )
