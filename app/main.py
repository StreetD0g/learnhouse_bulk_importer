from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .config import settings

APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=APP_DIR / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = settings.validation_errors()
    if missing:
        raise RuntimeError(f"Setze sichere Werte für: {', '.join(missing)}")
    settings.ensure_token_file()
    yield


app = FastAPI(
    title="LearnHouse Course Importer",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or "invalid-unconfigured-secret",
    https_only=settings.cookie_secure,
    same_site="lax",
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


def authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


def dashboard_context(request: Request) -> dict[str, object]:
    return {
        "learnhouse_url": settings.learnhouse_url,
        "org_id": settings.learnhouse_org_id,
        "org_slug": settings.learnhouse_org_slug,
        "csrf_token": request.session["csrf_token"],
        "connection_configured": settings.has_api_token(),
        "token_file": str(settings.learnhouse_token_file),
    }


@app.get("/healthz", include_in_schema=False)
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    if authenticated(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login(request: Request, username: str = Form(), password: str = Form()):
    valid = secrets.compare_digest(username, settings.importer_user) and secrets.compare_digest(
        password, settings.importer_password
    )
    if not valid:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Benutzername oder Passwort ist nicht korrekt."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session.clear()
    request.session.update(
        authenticated=True,
        csrf_token=secrets.token_urlsafe(32),
    )
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout", include_in_schema=False)
def logout(request: Request, csrf_token: str = Form()):
    expected = request.session.get("csrf_token", "")
    if authenticated(request) and secrets.compare_digest(csrf_token, expected):
        request.session.clear()
    return redirect_to_login()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    if not authenticated(request):
        return redirect_to_login()
    return templates.TemplateResponse(request, "dashboard.html", dashboard_context(request))


@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def connection_settings(request: Request):
    if not authenticated(request):
        return redirect_to_login()
    return templates.TemplateResponse(request, "settings.html", dashboard_context(request))

