from pathlib import Path

from app.db import ImportStore
from app.scanner import Chapter, Course, Lesson


def test_store_persists_job_progress_without_secrets(tmp_path: Path) -> None:
    store = ImportStore(tmp_path / "data" / "importer.sqlite3")
    lesson = Lesson("Welcome", "/imports/course/01 Welcome.mp4", "01 Welcome.mp4", "video", 12)
    course = Course("course", "/imports/course", "Course", "", "", "", False, None, [Chapter("Start", "01 Start", [lesson])], [])

    store.create_job("job-1", {"course_folders": ["course"], "publish": False}, [course])
    store.update_lesson("job-1", "course", "01 Welcome.mp4", status="success", activity_uuid="activity-1")

    job = store.job("job-1")
    assert job is not None
    assert "token" not in str(job["payload"]).casefold()
    assert store.progress("job-1") == (1, 1)
