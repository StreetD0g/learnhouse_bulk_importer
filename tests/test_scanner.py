from pathlib import Path

from app.scanner import clean_title, scan_root


def test_clean_title_removes_common_number_prefixes() -> None:
    assert clean_title("001 Willkommen.mp4") == "Willkommen"
    assert clean_title("01 - Grundlagen") == "Grundlagen"
    assert clean_title("10. Troubleshooting") == "Troubleshooting"


def test_scan_course_detects_media_and_skipped_files(tmp_path: Path) -> None:
    course = tmp_path / "01 Example Course"
    first = course / "01 Einstieg"
    second = course / "10 Abschluss"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "001 Willkommen.mp4").write_bytes(b"video")
    (first / "002 Handout.pdf").write_bytes(b"pdf")
    (first / "notes.docx").write_bytes(b"document")
    (second / "001 Ende.webm").write_bytes(b"webm")
    (course / "course.json").write_text('{"library_path":"IT/Grundlagen"}', encoding="utf-8")

    courses = scan_root(tmp_path)

    assert len(courses) == 1
    scanned = courses[0]
    assert scanned.name == "Example Course"
    assert [chapter.name for chapter in scanned.chapters] == ["Einstieg", "Abschluss"]
    assert scanned.to_dict()["lesson_count"] == 3
    assert scanned.library_path == "IT/Grundlagen"
    assert scanned.skipped == ["01 Einstieg/notes.docx"]


def test_scan_root_does_not_create_missing_read_only_directory(tmp_path: Path) -> None:
    missing = tmp_path / "not-mounted"
    assert scan_root(missing) == []
    assert not missing.exists()
