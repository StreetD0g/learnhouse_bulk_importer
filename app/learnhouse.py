from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .config import LearnHouseTarget, Settings


class LearnHouseError(RuntimeError):
    """An API error whose message is safe to show in the importer UI."""


class LearnHouseClient:
    def __init__(
        self,
        settings: Settings,
        *,
        target: LearnHouseTarget | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        selected = target or next(iter(settings.learnhouse_targets()), None)
        if not selected:
            raise LearnHouseError("Kein LearnHouse-API-Token konfiguriert.")
        base_url = selected.url.rstrip("/")
        self.api_url = base_url if base_url.endswith("/api/v1") else f"{base_url}/api/v1"
        self.org_id = selected.org_id
        self.org_slug = selected.org_slug
        self.org_label = selected.label
        self._token = selected.token
        self._http = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=30.0, read=21600.0, write=21600.0, pool=60.0),
            transport=transport,
        )

    def __enter__(self) -> "LearnHouseClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise LearnHouseError("Kein LearnHouse-API-Token konfiguriert.")
        return {"Authorization": f"Bearer {self._token}"}

    def _redact(self, value: object) -> str:
        message = str(value)
        if self._token:
            message = message.replace(self._token, "[REDACTED]")
        return message.replace("Authorization", "[REDACTED HEADER]")

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        detail: object = response.text
        try:
            payload = response.json()
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        except ValueError:
            pass
        raise LearnHouseError(f"LearnHouse API {response.status_code}: {self._redact(detail)}")

    def _request(self, method: str, path: str, *, retry: bool = False, **kwargs: Any) -> httpx.Response:
        attempts = 3 if retry else 1
        last_error: httpx.HTTPError | None = None
        for attempt in range(attempts):
            try:
                response = self._http.request(
                    method,
                    f"{self.api_url}{path}",
                    headers={**self._headers(), **kwargs.pop("headers", {})},
                    **kwargs,
                )
                if retry and response.status_code in {502, 503, 504} and attempt < attempts - 1:
                    time.sleep(2**attempt)
                    continue
                self._raise_for_status(response)
                return response
            except httpx.HTTPError as error:
                last_error = error
                if attempt < attempts - 1:
                    time.sleep(2**attempt)
        raise LearnHouseError(f"LearnHouse-Verbindung fehlgeschlagen: {self._redact(last_error)}")

    def test_connection(self) -> dict[str, object]:
        courses = self.list_courses(limit=1)
        folders = self._folders(None)
        return {
            "ok": True,
            "server": self.api_url.removesuffix("/api/v1"),
            "organization": {"id": self.org_id, "slug": self.org_slug},
            "courses_readable": True,
            "folders_readable": True,
            "sample_count": len(courses),
            "folder_sample_count": len(folders),
        }

    def list_courses(self, limit: int = 100) -> list[dict[str, Any]]:
        path = f"/courses/org_slug/{quote(self.org_slug, safe='')}/page/1/limit/{limit}"
        result = self._request("GET", path, retry=True).json()
        return result if isinstance(result, list) else []

    def create_course(
        self,
        *,
        name: str,
        description: str,
        about: str,
        thumbnail: str | None,
    ) -> dict[str, Any]:
        data = {
            "name": name,
            "description": description,
            "about": about,
            "public": "false",
            "thumbnail_type": "image",
        }
        handle = None
        try:
            files = None
            if thumbnail:
                path = Path(thumbnail)
                handle = path.open("rb")
                files = {
                    "thumbnail": (
                        path.name,
                        handle,
                        mimetypes.guess_type(path.name)[0] or "image/png",
                    )
                }
            return self._request(
                "POST",
                f"/courses/?org_id={quote(str(self.org_id), safe='')}",
                data=data,
                files=files,
            ).json()
        finally:
            if handle:
                handle.close()

    def create_chapter(self, course_id: int, name: str) -> dict[str, Any]:
        payload = {
            "name": name,
            "description": "",
            "course_id": course_id,
            "org_id": int(self.org_id),
            "lock_type": "authenticated",
        }
        return self._request("POST", "/chapters/", json=payload).json()

    def upload_video(self, chapter_id: int, title: str, source: str) -> dict[str, Any]:
        path = Path(source)
        mime = "video/mp4" if path.suffix.casefold() == ".mp4" else "video/webm"
        with path.open("rb") as handle:
            return self._request(
                "POST",
                "/activities/video",
                data={
                    "name": title,
                    "chapter_id": str(chapter_id),
                    "details": json.dumps({"startTime": 0, "endTime": None, "autoplay": False, "muted": False}),
                },
                files={"video_file": (path.name, handle, mime)},
            ).json()

    def upload_pdf(self, chapter_id: int, title: str, source: str) -> dict[str, Any]:
        path = Path(source)
        with path.open("rb") as handle:
            return self._request(
                "POST",
                "/activities/documentpdf",
                data={"name": title, "chapter_id": str(chapter_id)},
                files={"pdf_file": (path.name, handle, "application/pdf")},
            ).json()

    def update_activity(self, activity_uuid: str, *, published: bool) -> None:
        self._request("PUT", f"/activities/{quote(activity_uuid, safe='')}", json={"published": published})

    def update_course(self, course_uuid: str, *, published: bool) -> None:
        self._request("PUT", f"/courses/{quote(course_uuid, safe='')}", json={"published": published})

    def _folders(self, parent_uuid: str | None) -> list[dict[str, Any]]:
        suffix = f"?parent_folder_uuid={quote(parent_uuid, safe='')}" if parent_uuid else ""
        result = self._request(
            "GET",
            f"/folders/org/{quote(str(self.org_id), safe='')}/page/1/limit/100{suffix}",
            retry=True,
        ).json()
        return result if isinstance(result, list) else []

    def ensure_library_path(self, library_path: str) -> str | None:
        parent_uuid: str | None = None
        for name in (part.strip() for part in library_path.replace("\\", "/").split("/")):
            if not name:
                continue
            existing = self._folders(parent_uuid)
            match = next(
                (folder for folder in existing if str(folder.get("name", "")).casefold() == name.casefold()),
                None,
            )
            if match:
                parent_uuid = str(match["folder_uuid"])
                continue
            created = self._request(
                "POST",
                "/folders/",
                json={
                    "name": name,
                    "public": False,
                    "description": "",
                    "color": "blue",
                    "org_id": int(self.org_id),
                    "parent_folder_uuid": parent_uuid,
                },
            ).json()
            parent_uuid = str(created["folder_uuid"])
        return parent_uuid

    def place_course_in_library(self, course_uuid: str, library_path: str) -> None:
        folder_uuid = self.ensure_library_path(library_path)
        target = f"/folders/{quote(folder_uuid, safe='')}" if folder_uuid else f"/folders/org/{quote(str(self.org_id), safe='')}"
        self._request("POST", f"{target}/content?resource_uuid={quote(course_uuid, safe='')}&position=0")
