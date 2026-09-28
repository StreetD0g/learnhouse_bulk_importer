from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import ImportStore
from .importer import ImportRunner
from .learnhouse import LearnHouseClient, LearnHouseError
from .scanner import scan_root

APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=APP_DIR / "templates")
store = ImportStore(settings.data_dir / "importer.sqlite3")
executor = ThreadPoolExecutor(max_workers=settings.import_workers, thread_name_prefix="course-import")


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = settings.validation_errors()
    if missing:
        raise RuntimeError(f"Setze sichere Werte für: {', '.join(missing)}")
    settings.ensure_token_file()
    store.mark_running_as_interrupted()
    yield
    executor.shutdown(wait=False, cancel_futures=False)


app = FastAPI(title="LearnHouse Course Importer", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or "invalid-unconfigured-secret",
    https_only=settings.cookie_secure,
    same_site="lax",
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


class ImportRequest(BaseModel):
    course_folders: list[str] = Field(min_length=1, max_length=200)
    target_id: str = Field(min_length=1, max_length=30)
    library_path: str = Field(default="", max_length=500)
    publish: bool = False
    skip_duplicates: bool = True


class ConnectionTestRequest(BaseModel):
    target_id: str | None = Field(default=None, max_length=30)


def authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


def require_api_login(request: Request) -> None:
    if not authenticated(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Anmeldung erforderlich")


def scan_courses() -> list[Any]:
    return scan_root(settings.import_root)


def configured_target(target_id: str | None = None):
    targets = settings.learnhouse_targets()
    if not targets:
        raise LearnHouseError("Kein LearnHouse-API-Token konfiguriert.")
    if target_id is None and len(targets) == 1:
        return targets[0]
    target = next((candidate for candidate in targets if candidate.id == target_id), None)
    if not target:
        raise LearnHouseError("Das gewählte LearnHouse-Ziel ist nicht mehr konfiguriert.")
    return target


def dashboard_context(request: Request) -> dict[str, object]:
    courses = scan_courses()
    jobs = store.jobs()
    return {
        "learnhouse_url": settings.learnhouse_url,
        "org_id": settings.learnhouse_org_id,
        "org_slug": settings.learnhouse_org_slug,
        "csrf_token": request.session["csrf_token"],
        "connection_configured": settings.has_api_token(),
        "token_file": str(settings.learnhouse_token_file),
        "summary": {
            "ready": len(courses),
            "running": sum(job["status"] == "running" for job in jobs),
            "success": sum(job["status"] == "success" for job in jobs),
            "problems": sum(job["status"] in {"partial", "failed", "interrupted"} for job in jobs),
        },
    }


def start_job(job_id: str) -> None:
    try:
        job = store.job(job_id)
        if not job:
            return
        target = configured_target(job["payload"].get("target_id"))
        with LearnHouseClient(settings, target=target) as client:
            ImportRunner(store, client, str(settings.import_root)).run(job_id)
    except LearnHouseError as error:
        store.update_job(job_id, status="failed", message=str(error), log_entry=f"FEHLER: {error}")
    except Exception:
        store.update_job(
            job_id,
            status="failed",
            message="Unerwarteter Importfehler. Details im Container-Log prüfen.",
            log_entry="FEHLER: Unerwarteter Importfehler",
        )


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
    request.session.update(authenticated=True, csrf_token=secrets.token_urlsafe(32))
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


@app.get("/api/scan", include_in_schema=False)
def api_scan(request: Request) -> dict[str, object]:
    require_api_login(request)
    return {"courses": [course.to_dict() for course in scan_courses()]}


@app.post("/api/connection/test", include_in_schema=False)
def api_test_connection(request: Request, body: ConnectionTestRequest | None = None) -> dict[str, object]:
    require_api_login(request)
    try:
        with LearnHouseClient(settings, target=configured_target(body.target_id if body else None)) as client:
            return client.test_connection()
    except LearnHouseError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error


@app.get("/api/targets", include_in_schema=False)
def api_targets(request: Request) -> dict[str, object]:
    require_api_login(request)
    targets = settings.learnhouse_targets()
    return {
        "targets": [target.public() for target in targets],
        "selection_required": len(targets) > 1,
    }


@app.get("/api/courses/{folder_name}/thumbnail", include_in_schema=False)
def api_thumbnail(request: Request, folder_name: str):
    require_api_login(request)
    course = next((course for course in scan_courses() if course.folder_name == folder_name), None)
    if not course or not course.thumbnail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kein Kursbild vorhanden")
    return FileResponse(course.thumbnail)


@app.get("/api/jobs", include_in_schema=False)
def api_jobs(request: Request) -> dict[str, object]:
    require_api_login(request)
    return {"jobs": store.jobs()}


@app.get("/api/jobs/{job_id}", include_in_schema=False)
def api_job(request: Request, job_id: str) -> dict[str, object]:
    require_api_login(request)
    job = store.job(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import nicht gefunden")
    return job


@app.post("/api/import", include_in_schema=False)
def api_import(request: Request, body: ImportRequest) -> dict[str, str]:
    require_api_login(request)
    try:
        configured_target(body.target_id)
    except LearnHouseError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    available = {course.folder_name: course for course in scan_courses()}
    missing = [folder for folder in body.course_folders if folder not in available]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Kursordner nicht gefunden: {', '.join(missing)}")
    selected = [available[folder] for folder in body.course_folders]
    job_id = secrets.token_hex(12)
    store.create_job(job_id, body.model_dump(), selected)
    executor.submit(start_job, job_id)
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/resume", include_in_schema=False)
def api_resume_job(request: Request, job_id: str) -> dict[str, str]:
    require_api_login(request)
    if not settings.has_api_token():
        raise HTTPException(status.HTTP_409_CONFLICT, "Kein API-Token konfiguriert")
    job = store.job(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import nicht gefunden")
    if job["status"] == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "Import läuft bereits")
    store.update_job(job_id, status="queued", message="Wiederaufnahme wird vorbereitet", log_entry="Wiederaufnahme angefordert")
    executor.submit(start_job, job_id)
    return {"job_id": job_id}
