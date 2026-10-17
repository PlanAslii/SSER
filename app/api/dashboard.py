"""Dashboard overview route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_lang, get_theme
from app.core.database import get_db
from app.core.i18n import t
from app.models.admin import Administrator
from app.models.connection import ActiveConnection, AuthLog
from app.services.metrics_service import MetricsService
from app.services.ssh_service import SSHService

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin: Administrator = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    lang = get_lang(request, admin)
    theme = get_theme(request, admin)
    ssh = SSHService(db)
    metrics = MetricsService(db)
    counts = ssh.count_by_status()
    snapshot = metrics.current_snapshot()
    active_sessions = db.query(ActiveConnection).count()

    # Auth chart data (last 7 days)
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    since = datetime.now(timezone.utc) - timedelta(days=7)
    auth_rows = (
        db.query(
            func.date(AuthLog.created_at).label("day"),
            AuthLog.success,
            func.count(AuthLog.id),
        )
        .filter(AuthLog.created_at >= since)
        .group_by(func.date(AuthLog.created_at), AuthLog.success)
        .all()
    )
    auth_chart = {"labels": [], "success": [], "failed": []}
    # simplified: build day map
    day_map: dict = {}
    for day, success, count in auth_rows:
        key = str(day)
        if key not in day_map:
            day_map[key] = {"success": 0, "failed": 0}
        if success:
            day_map[key]["success"] = count
        else:
            day_map[key]["failed"] = count
    for day in sorted(day_map.keys()):
        auth_chart["labels"].append(day)
        auth_chart["success"].append(day_map[day]["success"])
        auth_chart["failed"].append(day_map[day]["failed"])

    status_chart = {
        "labels": [t("active", lang), t("disabled", lang), t("expired", lang)],
        "values": [
            counts.get("active", 0),
            counts.get("disabled", 0),
            counts.get("expired", 0),
        ],
    }

    return _templates(request).TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin": admin,
            "lang": lang,
            "dir": "rtl" if lang == "fa" else "ltr",
            "theme": theme,
            "t": lambda k: t(k, lang),
            "page": "dashboard",
            "counts": counts,
            "snapshot": snapshot,
            "active_sessions": active_sessions,
            "auth_chart": auth_chart,
            "status_chart": status_chart,
        },
    )
