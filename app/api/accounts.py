"""SSH account management routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_lang, get_theme
from app.core.database import get_db
from app.core.i18n import t
from app.models.admin import Administrator
from app.services.ssh_service import SSHService, SSHServiceError

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/accounts", response_class=HTMLResponse)
async def account_list(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    ssh = SSHService(db)
    limit = 25
    offset = (page - 1) * limit
    items, total = ssh.list_accounts(search=q, status=status, offset=offset, limit=limit)
    pages = max(1, (total + limit - 1) // limit)
    return _templates(request).TemplateResponse(
        "ssh/accounts.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "accounts",
            "accounts": items,
            "total": total,
            "current_page": page,
            "pages": pages,
            "search": q or "",
            "status_filter": status or "",
        },
    )


@router.get("/accounts/create", response_class=HTMLResponse)
async def account_create_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    return _templates(request).TemplateResponse(
        "ssh/account_form.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "accounts",
            "account": None,
            "error": None,
            "mode": "create",
        },
    )


@router.post("/accounts/create", response_class=HTMLResponse)
async def account_create_submit(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(""),
    public_key: str = Form(""),
    display_name: str = Form(""),
    email: str = Form(""),
    max_sessions: int = Form(5),
    expires_at: str = Form(""),
    notes: str = Form(""),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    ssh = SSHService(db)
    exp = None
    if expires_at.strip():
        try:
            exp = datetime.fromisoformat(expires_at.strip())
        except ValueError:
            exp = None
    try:
        ssh.create_account(
            username=username.strip(),
            password=password or None,
            public_key=public_key.strip() or None,
            display_name=display_name.strip() or None,
            email=email.strip() or None,
            max_sessions=max_sessions,
            expires_at=exp,
            notes=notes.strip() or None,
            created_by=admin.username,
        )
        return RedirectResponse("/accounts", status_code=302)
    except SSHServiceError as exc:
        return _templates(request).TemplateResponse(
            "ssh/account_form.html",
            {
                "request": request,
                "admin": admin,
                "lang": lang,
                "dir": "rtl" if lang == "fa" else "ltr",
                "theme": theme,
                "t": lambda k: t(k, lang),
                "page": "accounts",
                "account": None,
                "error": str(exc),
                "mode": "create",
            },
            status_code=400,
        )


@router.get("/accounts/{account_id}", response_class=HTMLResponse)
async def account_detail(
    account_id: int,
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    ssh = SSHService(db)
    account = ssh.get_account(account_id)
    if not account:
        return RedirectResponse("/accounts", status_code=302)
    return _templates(request).TemplateResponse(
        "ssh/account_detail.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "accounts",
            "account": account,
        },
    )


@router.get("/accounts/{account_id}/edit", response_class=HTMLResponse)
async def account_edit_page(
    account_id: int,
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    ssh = SSHService(db)
    account = ssh.get_account(account_id)
    if not account:
        return RedirectResponse("/accounts", status_code=302)
    return _templates(request).TemplateResponse(
        "ssh/account_form.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "accounts",
            "account": account,
            "error": None,
            "mode": "edit",
        },
    )


@router.post("/accounts/{account_id}/edit", response_class=HTMLResponse)
async def account_edit_submit(
    account_id: int,
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    password: str = Form(""),
    display_name: str = Form(""),
    email: str = Form(""),
    max_sessions: int = Form(5),
    expires_at: str = Form(""),
    notes: str = Form(""),
    status: str = Form("active"),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    ssh = SSHService(db)
    account = ssh.get_account(account_id)
    if not account:
        return RedirectResponse("/accounts", status_code=302)
    exp = None
    if expires_at.strip():
        try:
            exp = datetime.fromisoformat(expires_at.strip())
        except ValueError:
            exp = None
    try:
        kwargs = {
            "display_name": display_name.strip() or None,
            "email": email.strip() or None,
            "max_sessions": max_sessions,
            "expires_at": exp,
            "notes": notes.strip() or None,
            "status": status,
            "updated_by": admin.username,
        }
        if password:
            kwargs["password"] = password
        ssh.update_account(account, **kwargs)
        return RedirectResponse(f"/accounts/{account_id}", status_code=302)
    except SSHServiceError as exc:
        return _templates(request).TemplateResponse(
            "ssh/account_form.html",
            {
                "request": request,
                "admin": admin,
                "lang": lang,
                "dir": "rtl" if lang == "fa" else "ltr",
                "theme": theme,
                "t": lambda k: t(k, lang),
                "page": "accounts",
                "account": account,
                "error": str(exc),
                "mode": "edit",
            },
            status_code=400,
        )


@router.post("/accounts/{account_id}/disable")
async def account_disable(
    account_id: int,
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ssh = SSHService(db)
    account = ssh.get_account(account_id)
    if account:
        ssh.disable_account(account, actor=admin.username)
    return RedirectResponse("/accounts", status_code=302)


@router.post("/accounts/{account_id}/enable")
async def account_enable(
    account_id: int,
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ssh = SSHService(db)
    account = ssh.get_account(account_id)
    if account:
        try:
            ssh.enable_account(account, actor=admin.username)
        except SSHServiceError:
            pass
    return RedirectResponse("/accounts", status_code=302)


@router.post("/accounts/{account_id}/delete")
async def account_delete(
    account_id: int,
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    ssh = SSHService(db)
    account = ssh.get_account(account_id)
    if account:
        ssh.delete_account(account, actor=admin.username)
    return RedirectResponse("/accounts", status_code=302)
