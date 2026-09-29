# Course folder layout

Place each importable course in its own direct subfolder of `imports/`:

```text
imports/
└── Example course/
    ├── course.json
    ├── thumbnail.png
    ├── 01 Getting started/
    │   ├── 001 Welcome.mp4
    │   └── 002 Course overview.mp4
    └── 02 Fundamentals/
        ├── 001 Introduction.webm
        └── 002 Handout.pdf
```

## Mapping rules

- The top-level source folder becomes one LearnHouse course.
- Each direct subfolder becomes one chapter.
- Supported files found inside a chapter folder are lessons in that chapter.
- Supported media files stored directly in the course folder are put in a
  chapter named `General` unless `root_chapter_name` is set in `course.json`.
- Numeric prefixes determine natural order and are removed from the visible
  title.

Supported lesson files are `.mp4`, `.webm`, and `.pdf`. Supported thumbnail
files are `.jpg`, `.jpeg`, `.png`, and `.webp`. Other files are shown as
skipped during scanning and are not uploaded.

## Optional `course.json`

Use `course.json` in the course root to override detected metadata:

```json
{
  "name": "Example course",
  "description": "A short course description.",
  "about": "Additional information for learners.",
  "library_path": "Department/Topic",
  "thumbnail": "thumbnail.png",
  "publish": false,
  "root_chapter_name": "General"
}
```

All fields are optional. `thumbnail` must refer to an image inside the same
course folder. The importer rejects paths outside that folder.

## Publishing and duplicates

The import screen can publish a course after a fully successful import. A
course can also set `"publish": true` in `course.json`.

Duplicate detection compares course names against the selected LearnHouse
target. It can be disabled in the import UI when a deliberate repeat import is
required.
