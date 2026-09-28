from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

VIDEO_EXTENSIONS = {".mp4", ".webm"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | PDF_EXTENSIONS
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
THUMBNAIL_STEMS = {"thumbnail", "cover", "course", "poster"}
IGNORED_NAMES = {"course.json", ".ds_store", "thumbs.db", "desktop.ini"}
NUMBER_PREFIX = re.compile(r"^\s*(?:\[?\d{1,4}\]?)(?:\s*[-._)]\s*|\s+)?")


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def clean_title(value: str) -> str:
    name = Path(value).name
    suffix = Path(name).suffix.casefold()
    stem = (name[: -len(suffix)] if suffix in SUPPORTED_EXTENSIONS | IMAGE_EXTENSIONS else name).replace("_", " ").strip()
    cleaned = NUMBER_PREFIX.sub("", stem).strip(" -_.")
    return re.sub(r"\s+", " ", cleaned) or stem


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _visible(path: Path) -> bool:
    return not path.name.startswith(".") and path.name.casefold() not in IGNORED_NAMES


def _sorted(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: natural_key(path.name))


@dataclass(frozen=True)
class Lesson:
    title: str
    path: str
    relative_path: str
    kind: str
    size: int

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["size_human"] = human_size(self.size)
        return result


@dataclass(frozen=True)
class Chapter:
    name: str
    source_dir: str
    lessons: list[Lesson]

    def to_dict(self) -> dict[str, object]:
        size = sum(lesson.size for lesson in self.lessons)
        return {
            "name": self.name,
            "source_dir": self.source_dir,
            "lesson_count": len(self.lessons),
            "size": size,
            "size_human": human_size(size),
            "lessons": [lesson.to_dict() for lesson in self.lessons],
        }


@dataclass(frozen=True)
class Course:
    folder_name: str
    path: str
    name: str
    description: str
    about: str
    library_path: str
    publish: bool
    thumbnail: str | None
    chapters: list[Chapter]
    skipped: list[str]

    def to_dict(self) -> dict[str, object]:
        size = sum(lesson.size for chapter in self.chapters for lesson in chapter.lessons)
        return {
            "folder_name": self.folder_name,
            "path": self.path,
            "name": self.name,
            "description": self.description,
            "about": self.about,
            "library_path": self.library_path,
            "publish": self.publish,
            "thumbnail": self.thumbnail,
            "thumbnail_name": Path(self.thumbnail).name if self.thumbnail else None,
            "chapter_count": len(self.chapters),
            "lesson_count": sum(len(chapter.lessons) for chapter in self.chapters),
            "size": size,
            "size_human": human_size(size),
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "skipped": self.skipped,
            "skipped_count": len(self.skipped),
        }


def _load_metadata(course_dir: Path) -> tuple[dict[str, object], list[str]]:
    metadata_file = course_dir / "course.json"
    if not metadata_file.is_file():
        return {}, []
    try:
        data = json.loads(metadata_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}, ["course.json: JSON-Objekt erwartet"]
        return data, []
    except (OSError, json.JSONDecodeError):
        return {}, ["course.json: ungültiges JSON"]


def _thumbnail(course_dir: Path, metadata: dict[str, object]) -> Path | None:
    requested = metadata.get("thumbnail")
    if isinstance(requested, str) and requested.strip():
        candidate = (course_dir / requested).resolve()
        try:
            candidate.relative_to(course_dir.resolve())
        except ValueError:
            return None
        if candidate.is_file() and candidate.suffix.casefold() in IMAGE_EXTENSIONS:
            return candidate
    for path in _sorted(path for path in course_dir.iterdir() if path.is_file()):
        if path.suffix.casefold() in IMAGE_EXTENSIONS and path.stem.casefold() in THUMBNAIL_STEMS:
            return path
    return None


def _lesson(path: Path, course_dir: Path) -> Lesson | None:
    extension = path.suffix.casefold()
    if extension not in SUPPORTED_EXTENSIONS:
        return None
    return Lesson(
        title=clean_title(path.name),
        path=str(path),
        relative_path=path.relative_to(course_dir).as_posix(),
        kind="video" if extension in VIDEO_EXTENSIONS else "pdf",
        size=path.stat().st_size,
    )


def _scan_files(paths: Iterable[Path], course_dir: Path, skipped: list[str]) -> list[Lesson]:
    lessons: list[Lesson] = []
    for path in _sorted(path for path in paths if _visible(path)):
        lesson = _lesson(path, course_dir)
        if lesson:
            lessons.append(lesson)
        elif path.suffix.casefold() not in IMAGE_EXTENSIONS:
            skipped.append(path.relative_to(course_dir).as_posix())
    return lessons


def scan_course(course_dir: Path) -> Course:
    metadata, skipped = _load_metadata(course_dir)
    thumbnail = _thumbnail(course_dir, metadata)
    chapters: list[Chapter] = []

    root_files = [path for path in course_dir.iterdir() if path.is_file() and path != thumbnail]
    root_lessons = _scan_files(root_files, course_dir, skipped)
    if root_lessons:
        root_name = metadata.get("root_chapter_name")
        chapters.append(Chapter(str(root_name) if isinstance(root_name, str) else "Allgemein", ".", root_lessons))

    for directory in _sorted(path for path in course_dir.iterdir() if path.is_dir() and _visible(path)):
        files = [path for path in directory.rglob("*") if path.is_file()]
        lessons = _scan_files(files, course_dir, skipped)
        if lessons:
            chapters.append(Chapter(clean_title(directory.name), directory.name, lessons))

    def text(name: str, fallback: str = "") -> str:
        value = metadata.get(name, fallback)
        return value.strip() if isinstance(value, str) else fallback

    return Course(
        folder_name=course_dir.name,
        path=str(course_dir),
        name=text("name", clean_title(course_dir.name)),
        description=text("description"),
        about=text("about", text("description")),
        library_path=text("library_path"),
        publish=metadata.get("publish") is True,
        thumbnail=str(thumbnail) if thumbnail else None,
        chapters=chapters,
        skipped=skipped,
    )


def scan_root(import_root: Path) -> list[Course]:
    """Scan an existing, read-only source directory without creating files."""
    if not import_root.is_dir():
        return []
    courses = []
    for directory in _sorted(path for path in import_root.iterdir() if path.is_dir() and _visible(path)):
        course = scan_course(directory)
        if course.chapters or course.skipped:
            courses.append(course)
    return courses
