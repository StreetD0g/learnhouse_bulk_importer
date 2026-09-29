# LearnHouse Course Importer

> [!WARNING]
> **AI-assisted and experimental.** This project is an early-stage importer
> built with substantial AI assistance. Back up every course source, test with
> non-critical data first, and review the code before using it in production.
> Use it at your own risk.

A self-hosted bulk importer for local LearnHouse course folders. It scans a
mounted source directory and creates courses, chapters, and learning
activities through the LearnHouse REST API.

> This project is not affiliated with, endorsed by, or supported by LearnHouse.

## Highlights

- Imports `.mp4`, `.webm`, and `.pdf` files from local course folders
- Creates courses, chapters, and nested LearnHouse library folders
- Shows a preview before importing and marks unsupported files visibly
- Supports one or more local LearnHouse API targets
- Persists import progress and can resume interrupted jobs
- Keeps API tokens out of Compose, the database, and the browser
- Can optionally remove a verified staging source after explicit confirmation

Currently out of scope: subtitles, audio-only files, Office files, SCORM,
direct LearnHouse database access, and direct writes to LearnHouse content
storage.

## Quick start

1. Clone the repository and open [`docker-compose.yml`](docker-compose.yml).
2. Replace `IMPORTER_PASSWORD` and `SESSION_SECRET` with strong, unique values.
3. Set the fallback `LEARNHOUSE_URL`, `LEARNHOUSE_ORG_ID`, and
   `LEARNHOUSE_ORG_SLUG` for a single target.
4. Start the importer:

   ```bash
   docker compose up -d --build
   ```

5. Add a LearnHouse API token to the newly created local file
   `config/learnhouse-importer.env`.
6. Open `http://HOST:8099`, sign in, test the connection, and scan the
   `imports/` folder.

The container deliberately refuses to start while the default password or
session-secret placeholders are still present.

For the complete walkthrough, see the [installation guide](docs/installation.md).

## Course folder at a glance

```text
imports/
└── Example course/
    ├── course.json                 # optional metadata
    ├── thumbnail.png               # optional thumbnail
    ├── 01 Getting started/
    │   ├── 001 Welcome.mp4
    │   └── 002 Course overview.mp4
    └── 02 Fundamentals/
        ├── 001 Introduction.webm
        └── 002 Handout.pdf
```

The top-level folder becomes a LearnHouse course. Each direct subfolder becomes
a chapter. Numeric prefixes such as `01`, `01 -`, `001`, and `001.` control the
natural sort order but are removed from visible titles.

See [course folder layout](docs/course-layout.md) for `course.json` metadata
and supported formats.

## Security model

- The importer has its own Compose-configured web login; it does not create a
  user database.
- LearnHouse tokens stay only in the local `config/` mount. They are never
  stored in SQLite or returned to the browser.
- The source folder is read-only by default. The optional cleanup mode is for a
  disposable staging folder only; it never deletes anything in LearnHouse.
- Local configuration, import sources, and `.env` files are ignored by Git and
  excluded from the Docker build context.

## Documentation

- [Installation and first import](docs/installation.md)
- [LearnHouse targets: external and local Docker setups](docs/learnhouse-targets.md)
- [Course folder layout and metadata](docs/course-layout.md)
- [Optional staging-source cleanup](docs/source-cleanup.md)

GitHub renders these Markdown guides directly in the repository. A GitHub Pages
site is not needed unless a separate documentation website is wanted later.

## Development and releases

- `dev` is the development branch.
- `prod` contains release-candidate and production-ready states only.
- Release candidates are created from `prod`, never directly from `dev`.
