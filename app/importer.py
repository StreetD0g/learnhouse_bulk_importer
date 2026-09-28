from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import ImportStore
from .learnhouse import LearnHouseClient, LearnHouseError
from .scanner import Course, scan_root


class ImportRunner:
    def __init__(self, store: ImportStore, client: LearnHouseClient, import_root: str) -> None:
        self.store = store
        self.client = client
        self.import_root = import_root

    def run(self, job_id: str) -> None:
        job = self.store.job(job_id)
        if not job:
            return
        payload: dict[str, Any] = job["payload"]
        courses = {course.folder_name: course for course in scan_root(Path(self.import_root))}
        selected = payload.get("course_folders", [])
        self.store.update_job(job_id, status="running", message="Import wird vorbereitet", log_entry="Import gestartet")
        target_names = {str(course.get("name", "")).casefold() for course in self.client.list_courses()}
        had_errors = False

        for folder_name in selected:
            course = courses.get(folder_name)
            if not course:
                self.store.update_course(job_id, folder_name, status="failed", error="Quellordner nicht mehr vorhanden")
                self.store.update_job(job_id, log_entry=f"FEHLER: Quellordner fehlt: {folder_name}")
                had_errors = True
                continue
            try:
                partial = self._run_course(job_id, course, payload, target_names)
                had_errors = had_errors or partial
            except LearnHouseError as error:
                self.store.update_course(job_id, folder_name, status="failed", error=str(error))
                self.store.update_job(job_id, log_entry=f"FEHLER: {course.name}: {error}")
                had_errors = True
            self._update_progress(job_id)

        self._update_progress(job_id)
        final_status = "partial" if had_errors else "success"
        self.store.update_job(
            job_id,
            status=final_status,
            progress=100,
            message="Import mit Fehlern abgeschlossen" if had_errors else "Import abgeschlossen",
            log_entry="Import abgeschlossen",
        )

    def _run_course(
        self, job_id: str, course: Course, payload: dict[str, Any], target_names: set[str]
    ) -> bool:
        record = self.store.course(job_id, course.folder_name)
        if not record:
            raise LearnHouseError("Importzustand für Kurs fehlt")
        if record["status"] == "success":
            return False
        if not record.get("course_uuid"):
            if payload.get("skip_duplicates", True) and course.name.casefold() in target_names:
                reason = "Kurs mit gleichem Namen existiert bereits"
                self.store.update_course(job_id, course.folder_name, status="skipped", error=reason)
                self.store.skip_lessons_for_course(job_id, course.folder_name, reason)
                self.store.update_job(job_id, message=f"Übersprungen: {course.name}", log_entry=f"SKIP: {course.name}")
                return False
            self.store.update_job(job_id, message=f"Erstelle Kurs: {course.name}", log_entry=f"KURS: {course.name}")
            created = self.client.create_course(
                name=course.name,
                description=course.description,
                about=course.about,
                thumbnail=course.thumbnail,
            )
            course_id = int(created["id"])
            course_uuid = str(created["course_uuid"])
            self.store.update_course(
                job_id,
                course.folder_name,
                status="importing",
                course_id=course_id,
                course_uuid=course_uuid,
                error=None,
            )
            target_names.add(course.name.casefold())
            record = self.store.course(job_id, course.folder_name)

        course_id = int(record["course_id"])
        course_uuid = str(record["course_uuid"])
        partial = False
        activity_uuids: list[str] = []

        for chapter in course.chapters:
            chapter_record = self.store.chapter(job_id, course.folder_name, chapter.source_dir)
            if not chapter_record:
                raise LearnHouseError(f"Importzustand für Kapitel fehlt: {chapter.name}")
            if not chapter_record.get("chapter_id"):
                self.store.update_job(job_id, message=f"Kapitel: {chapter.name}")
                created = self.client.create_chapter(course_id, chapter.name)
                self.store.update_chapter(
                    job_id,
                    course.folder_name,
                    chapter.source_dir,
                    status="importing",
                    chapter_id=int(created["id"]),
                    chapter_uuid=str(created.get("chapter_uuid", "")),
                    error=None,
                )
                chapter_record = self.store.chapter(job_id, course.folder_name, chapter.source_dir)

            chapter_id = int(chapter_record["chapter_id"])
            for lesson in chapter.lessons:
                lesson_record = self.store.lesson(job_id, course.folder_name, lesson.relative_path)
                if not lesson_record or lesson_record["status"] == "success":
                    if lesson_record and lesson_record.get("activity_uuid"):
                        activity_uuids.append(str(lesson_record["activity_uuid"]))
                    continue
                self.store.update_job(job_id, message=f"Upload: {lesson.title}")
                self.store.update_lesson(
                    job_id, course.folder_name, lesson.relative_path, status="uploading", error=None
                )
                try:
                    result = (
                        self.client.upload_video(chapter_id, lesson.title, lesson.path)
                        if lesson.kind == "video"
                        else self.client.upload_pdf(chapter_id, lesson.title, lesson.path)
                    )
                    activity_uuid = str(result.get("activity_uuid", ""))
                    self.store.update_lesson(
                        job_id,
                        course.folder_name,
                        lesson.relative_path,
                        status="success",
                        activity_uuid=activity_uuid or None,
                    )
                    if activity_uuid:
                        activity_uuids.append(activity_uuid)
                    self.store.update_job(job_id, log_entry=f"OK: {course.name} / {lesson.relative_path}")
                except (LearnHouseError, OSError) as error:
                    self.store.update_lesson(
                        job_id,
                        course.folder_name,
                        lesson.relative_path,
                        status="failed",
                        error=str(error),
                    )
                    self.store.update_job(job_id, log_entry=f"FEHLER: {lesson.relative_path}: {error}")
                    partial = True
                self._update_progress(job_id)

        if not partial:
            library_path = course.library_path or str(payload.get("library_path", ""))
            self.client.place_course_in_library(course_uuid, library_path)
            if payload.get("publish") or course.publish:
                for activity_uuid in activity_uuids:
                    self.client.update_activity(activity_uuid, published=True)
                self.client.update_course(course_uuid, published=True)
            self.store.update_course(job_id, course.folder_name, status="success", error=None)
        else:
            self.store.update_course(job_id, course.folder_name, status="partial")
        return partial

    def _update_progress(self, job_id: str) -> None:
        completed, total = self.store.progress(job_id)
        progress = min(99, int(completed / total * 100)) if total else 99
        self.store.update_job(job_id, progress=progress)
