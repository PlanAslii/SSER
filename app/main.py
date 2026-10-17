"""PlanAsli SSH Manager — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.core.config import get_settings
from app.core.database import get_db, init_db
from app.core.i18n import get_all, t
from app.api import auth, accounts, dashboard, updates, system, admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("planasli")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    init_db()
    logger.info("PlanAsli SSH Manager v%s starting", __version__)
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=False,
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["t"] = t
    templates.env.globals["app_version"] = __version__
    templates.env.globals["app_name"] = settings.app_name

    app.state.templates = templates
    app.state.settings = settings

    # Routers
    app.include_router(auth.router, tags=["auth"])
    app.include_router(dashboard.router, tags=["dashboard"])
    app.include_router(accounts.router, tags=["accounts"])
    app.include_router(updates.router, tags=["updates"])
    app.include_router(system.router, tags=["system"])
    app.include_router(admin.router, tags=["admin"])

    @app.get("/health", response_class=HTMLResponse)
    async def health():
        return HTMLResponse("ok", status_code=200)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        if request.session.get("admin_id"):
            return RedirectResponse("/dashboard", status_code=302)
        return RedirectResponse("/login", status_code=302)

    return app


app = create_app()
