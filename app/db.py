from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .scanner import Course


class ImportStore:
    """Persistent import state. Secrets are intentionally never accepted here."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  progress INTEGER NOT NULL DEFAULT 0,
                  message TEXT NOT NULL DEFAULT '',
                  payload TEXT NOT NULL DEFAULT '{}',
                  log TEXT NOT NULL DEFAULT '[]',
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS job_courses (
                  job_id TEXT NOT NULL,
                  folder_name TEXT NOT NULL,
                  source_path TEXT NOT NULL,
                  course_name TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  course_id INTEGER,
                  course_uuid TEXT,
                  error TEXT,
                  PRIMARY KEY (job_id, folder_name)
                );
                CREATE TABLE IF NOT EXISTS job_chapters (
                  job_id TEXT NOT NULL,
                  folder_name TEXT NOT NULL,
                  source_dir TEXT NOT NULL,
                  chapter_name TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  chapter_id INTEGER,
                  chapter_uuid TEXT,
                  error TEXT,
                  PRIMARY KEY (job_id, folder_name, source_dir)
                );
                CREATE TABLE IF NOT EXISTS job_lessons (
                  job_id TEXT NOT NULL,
                  folder_name TEXT NOT NULL,
                  relative_path TEXT NOT NULL,
                  chapter_source_dir TEXT NOT NULL,
                  title TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  size INTEGER NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  activity_uuid TEXT,
                  error TEXT,
                  PRIMARY KEY (job_id, folder_name, relative_path)
                );
                """
            )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        if "payload" in result:
            result["payload"] = json.loads(result["payload"] or "{}")
        if "log" in result:
            result["log"] = json.loads(result["log"] or "[]")
        return result

    def create_job(self, job_id: str, payload: dict[str, Any], courses: list[Course]) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO jobs (id, status, payload) VALUES (?, 'queued', ?)",
                (job_id, json.dumps(payload)),
            )
            for course in courses:
                connection.execute(
                    """
                    INSERT INTO job_courses (job_id, folder_name, source_path, course_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_id, course.folder_name, course.path, course.name),
                )
                for chapter in course.chapters:
                    connection.execute(
                        """
                        INSERT INTO job_chapters (job_id, folder_name, source_dir, chapter_name)
                        VALUES (?, ?, ?, ?)
                        """,
                        (job_id, course.folder_name, chapter.source_dir, chapter.name),
                    )
                    for lesson in chapter.lessons:
                        connection.execute(
                            """
                            INSERT INTO job_lessons
                            (job_id, folder_name, relative_path, chapter_source_dir, title, kind, size)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                job_id,
                                course.folder_name,
                                lesson.relative_path,
                                chapter.source_dir,
                                lesson.title,
                                lesson.kind,
                                lesson.size,
                            ),
                        )

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        log_entry: str | None = None,
    ) -> None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return
            log = json.loads(row["log"] or "[]")
            if log_entry:
                log.append(log_entry)
                log = log[-500:]
            connection.execute(
                """
                UPDATE jobs SET status = ?, progress = ?, message = ?, log = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (
                    status if status is not None else row["status"],
                    progress if progress is not None else row["progress"],
                    message if message is not None else row["message"],
                    json.dumps(log),
                    job_id,
                ),
            )

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row(row) if row else None

    def jobs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row(row) for row in rows]

    def source_import_states(self, source_paths: list[str]) -> dict[str, dict[str, object]]:
        """Return the useful, user-facing state for each currently scanned source.

        A source remains on disk after a successful import by design.  Therefore
        the scanner must not present it as a new, merely "ready" course again.
        A completed import takes precedence over older failed attempts for the
        same exact source folder.
        """
        if not source_paths:
            return {}
        placeholders = ", ".join("?" for _ in source_paths)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT job_courses.source_path, job_courses.status AS course_status,
                       jobs.status AS job_status, jobs.id AS job_id, jobs.created_at
                FROM job_courses
                JOIN jobs ON jobs.id = job_courses.job_id
                WHERE job_courses.source_path IN ({placeholders})
                ORDER BY jobs.created_at DESC, jobs.rowid DESC
                """,
                source_paths,
            ).fetchall()

        states: dict[str, dict[str, object]] = {}
        for row in rows:
            source_path = str(row["source_path"])
            is_success = row["job_status"] == "success" and row["course_status"] == "success"
            if is_success:
                states[source_path] = {
                    "status": "success",
                    "label": "Importiert",
                    "job_id": row["job_id"],
                }
                continue
            # Do not overwrite a known successful import with an older attempt.
            if source_path in states:
                continue
            if row["job_status"] in {"queued", "running"}:
                states[source_path] = {"status": "running", "label": "Import läuft", "job_id": row["job_id"]}
            elif row["job_status"] in {"partial", "failed", "interrupted"}:
                states[source_path] = {"status": "partial", "label": "Import prüfen", "job_id": row["job_id"]}

        return states

    def job_is_superseded(self, job_id: str) -> bool:
        """Whether all sources of a non-successful job later imported successfully."""
        with self._lock, self._connection() as connection:
            job = connection.execute("SELECT rowid, status, created_at FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job or job["status"] == "success":
                return False
            sources = connection.execute(
                "SELECT source_path FROM job_courses WHERE job_id = ?", (job_id,)
            ).fetchall()
            if not sources:
                return False
            for source in sources:
                successful = connection.execute(
                    """
                    SELECT 1
                    FROM job_courses
                    JOIN jobs AS successful_job ON successful_job.id = job_courses.job_id
                    WHERE job_courses.source_path = ?
                      AND successful_job.status = 'success'
                      AND job_courses.status = 'success'
                      AND (
                        successful_job.created_at > ?
                        OR (successful_job.created_at = ? AND successful_job.rowid > ?)
                      )
                    LIMIT 1
                    """,
                    (source["source_path"], job["created_at"], job["created_at"], job["rowid"]),
                ).fetchone()
                if not successful:
                    return False
            return True

    def courses_for_job(self, job_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM job_courses WHERE job_id = ? ORDER BY folder_name", (job_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_job_payload(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET payload = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(payload), job_id),
            )

    def course(self, job_id: str, folder_name: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM job_courses WHERE job_id = ? AND folder_name = ?", (job_id, folder_name)
            ).fetchone()
            return dict(row) if row else None

    def chapter(self, job_id: str, folder_name: str, source_dir: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT * FROM job_chapters WHERE job_id = ? AND folder_name = ? AND source_dir = ?""",
                (job_id, folder_name, source_dir),
            ).fetchone()
            return dict(row) if row else None

    def lesson(self, job_id: str, folder_name: str, relative_path: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT * FROM job_lessons WHERE job_id = ? AND folder_name = ? AND relative_path = ?""",
                (job_id, folder_name, relative_path),
            ).fetchone()
            return dict(row) if row else None

    def update_course(self, job_id: str, folder_name: str, **values: Any) -> None:
        self._update("job_courses", ("job_id", "folder_name"), (job_id, folder_name), values)

    def update_chapter(self, job_id: str, folder_name: str, source_dir: str, **values: Any) -> None:
        self._update(
            "job_chapters", ("job_id", "folder_name", "source_dir"), (job_id, folder_name, source_dir), values
        )

    def update_lesson(self, job_id: str, folder_name: str, relative_path: str, **values: Any) -> None:
        self._update(
            "job_lessons", ("job_id", "folder_name", "relative_path"), (job_id, folder_name, relative_path), values
        )

    def _update(
        self, table: str, keys: tuple[str, ...], key_values: tuple[object, ...], values: dict[str, Any]
    ) -> None:
        if not values:
            return
        columns = ", ".join(f"{column} = ?" for column in values)
        where = " AND ".join(f"{column} = ?" for column in keys)
        with self._lock, self._connection() as connection:
            connection.execute(
                f"UPDATE {table} SET {columns} WHERE {where}",
                (*values.values(), *key_values),
            )

    def progress(self, job_id: str) -> tuple[int, int]:
        with self._lock, self._connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM job_lessons WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
            completed = connection.execute(
                """SELECT COUNT(*) FROM job_lessons WHERE job_id = ? AND status IN ('success', 'skipped')""",
                (job_id,),
            ).fetchone()[0]
            return completed, total

    def skip_lessons_for_course(self, job_id: str, folder_name: str, reason: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE job_lessons SET status = 'skipped', error = ?
                WHERE job_id = ? AND folder_name = ? AND status = 'pending'
                """,
                (reason, job_id, folder_name),
            )

    def mark_running_as_interrupted(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE jobs SET status = 'interrupted', message = 'Container wurde während des Imports neu gestartet',
                updated_at = CURRENT_TIMESTAMP WHERE status = 'running'
                """
            )
