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
