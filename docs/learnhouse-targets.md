# LearnHouse targets

The importer calls the LearnHouse REST API from the server-side container. It
does not need browser CORS access and it does not need access to the LearnHouse
database or content directory.

## External LearnHouse instance

This is the default and recommended setup when LearnHouse and the importer run
on different hosts. Set the public HTTPS URL of LearnHouse in Compose or in the
numbered target entry:

```env
LEARNHOUSE_URL_1=https://learn.example.com
```

Make sure the reverse proxy in front of LearnHouse accepts the expected upload
sizes and long-running requests. For Nginx, review `client_max_body_size` and
the relevant proxy timeout settings. Any CDN, tunnel, or proxy in front of
LearnHouse must allow at least the same limits.

## Local Docker connection

If both services run on the same Docker host and the LearnHouse Compose project
exposes an external network named `learnhouse`, the importer can use the
internal service address instead of the public URL:

1. Copy `docker-compose.local.yml.example` to `docker-compose.local.yml`.
2. Confirm that the external Docker network `learnhouse` exists.
3. Start with both Compose files:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
   ```

The local override is ignored by Git so a public repository does not contain
host-specific network settings.

## Multiple targets

Use sequential numbers in `config/learnhouse-importer.env`:

```env
LEARNHOUSE_TOKEN_1=first-token
LEARNHOUSE_ORG_1=Example academy
LEARNHOUSE_URL_1=https://learn.example.com
LEARNHOUSE_ORG_ID_1=1
LEARNHOUSE_ORG_SLUG_1=default

LEARNHOUSE_TOKEN_2=second-token
LEARNHOUSE_ORG_2=Internal academy
LEARNHOUSE_URL_2=https://learn.internal.example
LEARNHOUSE_ORG_ID_2=7
LEARNHOUSE_ORG_SLUG_2=internal-academy
```

The importer asks for a target before importing when more than one token is
configured. A LearnHouse API token is organisation-scoped, so URL, organisation
ID, and organisation slug should be set for every target that differs from the
Compose fallback.

The importer only checks whether a token exists during page load. Token validity
is checked by **Test connection** and before importing.
