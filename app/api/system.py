"""System monitoring, connections, logs, backups routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_lang, get_theme
from app.core.database import get_db
from app.core.i18n import t
from app.models.admin import Administrator
from app.models.audit import AuditEvent
from app.models.connection import ActiveConnection, AuthLog, ConnectionHistory
from app.services.metrics_service import MetricsService

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/connections", response_class=HTMLResponse)
async def active_connections(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    items = db.query(ActiveConnection).order_by(ActiveConnection.started_at.desc()).limit(100).all()
    return _templates(request).TemplateResponse(
        "ssh/connections.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "connections",
            "connections": items,
        },
    )


@router.get("/connection-history", response_class=HTMLResponse)
async def connection_history(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    limit = 50
    offset = (page - 1) * limit
    items = (
        db.query(ConnectionHistory)
        .order_by(ConnectionHistory.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return _templates(request).TemplateResponse(
        "ssh/connection_history.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "connection_history",
            "history": items,
            "current_page": page,
        },
    )


@router.get("/auth-logs", response_class=HTMLResponse)
async def auth_logs(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    limit = 50
    offset = (page - 1) * limit
    items = (
        db.query(AuthLog)
        .order_by(AuthLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return _templates(request).TemplateResponse(
        "ssh/auth_logs.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "auth_logs",
            "logs": items,
            "current_page": page,
        },
    )


@router.get("/monitoring", response_class=HTMLResponse)
async def monitoring(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    metrics = MetricsService(db)
    snapshot = metrics.current_snapshot()
    history = metrics.history(hours=24)
    chart = {
        "labels": [m.recorded_at.strftime("%H:%M") for m in history],
        "cpu": [m.cpu_percent for m in history],
        "memory": [m.memory_percent for m in history],
    }
    return _templates(request).TemplateResponse(
        "system/monitoring.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "monitoring",
            "snapshot": snapshot,
            "chart": chart,
        },
    )


@router.get("/backups", response_class=HTMLResponse)
async def backups_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    from pathlib import Path
    settings = request.app.state.settings
    backup_dir = settings.backup_dir
    backups = []
    if backup_dir.exists():
        for p in sorted(backup_dir.iterdir(), reverse=True):
            if p.is_dir() or p.suffix in (".tar", ".gz", ".tgz", ".sql", ".db"):
                backups.append({"name": p.name, "path": str(p), "size": p.stat().st_size if p.is_file() else None})
    return _templates(request).TemplateResponse(
        "system/backups.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "backups",
            "backups": backups,
        },
    )


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    limit = 50
    offset = (page - 1) * limit
    items = (
        db.query(AuditEvent)
        .order_by(AuditEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return _templates(request).TemplateResponse(
        "system/audit.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "audit",
            "events": items,
            "current_page": page,
        },
    )


@router.get("/ssh-settings", response_class=HTMLResponse)
async def ssh_settings(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    return _templates(request).TemplateResponse(
        "ssh/settings.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "ssh_settings",
        },
    )


@router.get("/login-messages", response_class=HTMLResponse)
async def login_messages(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    return _templates(request).TemplateResponse(
        "ssh/login_messages.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "login_messages",
        },
    )


@router.get("/network", response_class=HTMLResponse)
async def network_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    return _templates(request).TemplateResponse(
        "system/network.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "network",
        },
    )


@router.get("/docs", response_class=HTMLResponse)
async def docs_page(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    return _templates(request).TemplateResponse(
        "admin/docs.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "docs",
        },
    )
