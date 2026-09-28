from pathlib import Path

from app.db import ImportStore
from app.importer import ImportRunner
from app.scanner import scan_root


class FakeLearnHouseClient:
    def __init__(self) -> None:
        self.course_creations = 0
        self.uploads = 0

    def list_courses(self):
        return []

    def create_course(self, **_):
        self.course_creations += 1
        return {"id": 42, "course_uuid": "course-uuid"}

    def create_chapter(self, *_):
        return {"id": 99, "chapter_uuid": "chapter-uuid"}

    def upload_video(self, *_):
        self.uploads += 1
        return {"activity_uuid": "activity-uuid"}

    def upload_pdf(self, *_):
        self.uploads += 1
        return {"activity_uuid": "activity-uuid"}

    def place_course_in_library(self, *_):
        return None

    def update_activity(self, *_ , **__):
        return None

    def update_course(self, *_ , **__):
        return None


def test_successful_job_does_not_reupload_on_resume(tmp_path: Path) -> None:
    source = tmp_path / "imports"
    lesson_dir = source / "Course" / "01 Start"
    lesson_dir.mkdir(parents=True)
    (lesson_dir / "001 Welcome.mp4").write_bytes(b"video")
    course = scan_root(source)[0]
    store = ImportStore(tmp_path / "data" / "importer.sqlite3")
    store.create_job("job", {"course_folders": ["Course"], "skip_duplicates": True}, [course])
    client = FakeLearnHouseClient()
    runner = ImportRunner(store, client, str(source))

    runner.run("job")
    runner.run("job")

    assert client.course_creations == 1
    assert client.uploads == 1
    assert store.job("job")["status"] == "success"
