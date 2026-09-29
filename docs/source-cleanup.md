# Optional staging-source cleanup

By default, the importer mounts `imports/` read-only. This protects the
original course files and no cleanup action is shown in the UI.

Enable cleanup only when `imports/` is a disposable staging directory with an
independent backup. Never use it for the only copy of a course.

## Enable cleanup

1. Copy `docker-compose.cleanup.yml.example` to `docker-compose.cleanup.yml`.
2. Start with both Compose files:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.cleanup.yml up -d
   ```

The copied local override is ignored by Git.

## What is deleted

After a fully successful import, History shows **Delete course source**. The UI
requires an explicit browser confirmation. The importer then removes only the
exact direct course folders recorded for that completed job.

It never deletes the LearnHouse course, chapters, or activities. Partial,
failed, interrupted, or already-cleaned jobs cannot use this action.
