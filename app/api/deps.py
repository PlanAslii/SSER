"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.admin import Administrator


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> Administrator:
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    admin = db.query(Administrator).filter(Administrator.id == admin_id, Administrator.is_active.is_(True)).first()
    if not admin:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return admin


def get_lang(request: Request, admin: Administrator | None = None) -> str:
    if admin and admin.language:
        return admin.language
    return request.session.get("language", "fa")


def get_theme(request: Request, admin: Administrator | None = None) -> str:
    if admin and admin.theme:
        return admin.theme
    return request.session.get("theme", "system")
