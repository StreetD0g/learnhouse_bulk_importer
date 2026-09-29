# Installation and first import

## Prerequisites

- Docker Engine with Docker Compose v2
- A reachable LearnHouse instance and an API token with the required import
  permissions
- A local folder containing one or more course folders

## 1. Prepare the project directory

Clone the repository, then create the two local mount directories:

```bash
git clone https://github.com/StreetD0g/learnhouse_bulk_importer.git
cd learnhouse_bulk_importer
mkdir -p imports config
```

On Windows, create `imports` and `config` in the cloned project folder with
Explorer or PowerShell instead.

## 2. Configure the web login and fallback target

Edit [`../docker-compose.yml`](../docker-compose.yml) before the first start.
Replace both placeholder values below with long, unique secrets that are not
reused elsewhere:

```yaml
IMPORTER_PASSWORD: "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD"
SESSION_SECRET: "CHANGE_ME_TO_A_LONG_RANDOM_SESSION_SECRET"
```

For a single LearnHouse target, also set its public HTTPS URL, organisation ID,
and organisation slug in the same file:

```yaml
LEARNHOUSE_URL: "https://learn.example.com"
LEARNHOUSE_ORG_ID: "1"
LEARNHOUSE_ORG_SLUG: "default"
```

Keep `COOKIE_SECURE` set to `false` only for direct LAN HTTP access. Set it to
`true` when the importer itself is served behind an HTTPS reverse proxy.

## 3. Start the importer

```bash
docker compose up -d --build
```

The first start creates `config/learnhouse-importer.env` if it does not yet
exist. It intentionally contains no API token.

## 4. Add the API token locally

Open `config/learnhouse-importer.env` and fill in the first target:

```env
LEARNHOUSE_TOKEN_1=replace-with-your-token
LEARNHOUSE_ORG_1=Example academy
LEARNHOUSE_URL_1=https://learn.example.com
LEARNHOUSE_ORG_ID_1=1
LEARNHOUSE_ORG_SLUG_1=default
```

`LEARNHOUSE_ORG_1` is only the visible label in the importer. It is optional;
without it, the UI displays `Token 1`. Do not commit this file. The `config/`
directory is already ignored by Git.

Restart the importer after changing the token file:

```bash
docker compose restart importer
```

## 5. Scan and import

1. Place course folders inside `imports/`.
2. Open `http://HOST:8099` and sign in with the web-login values from Compose.
3. Use **Test connection** to verify the LearnHouse target.
4. Use **Scan folder**, review the discovered course and chapter structure, then
   import a course.
5. Follow progress on the Imports page and inspect completed jobs in History.

The source mount is read-only by default, so imports cannot alter or remove the
original course files.

## Updating

Pull the desired Git revision, then rebuild and restart:

```bash
git pull
docker compose up -d --build
```

Keep the local `config/`, `imports/`, and Docker volume data in place during an
update.
