from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


def _value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _is_placeholder(value: str) -> bool:
    return not value or value.upper().startswith("CHANGE_ME")


@dataclass(frozen=True)
class Settings:
    importer_user: str
    importer_password: str
    session_secret: str
    cookie_secure: bool
    learnhouse_url: str
    learnhouse_org_id: str
    learnhouse_org_slug: str
    learnhouse_token_file: Path
    import_root: Path
    data_dir: Path
    import_workers: int
    import_source_writable: bool = False

    def _token_values(self) -> dict[str, str]:
        """Read the local token file without ever exporting its contents."""
        try:
            lines = self.learnhouse_token_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}

        values: dict[str, str] = {}
        for line in lines:
            entry = line.strip()
            if not entry or entry.startswith("#") or "=" not in entry:
                continue
            key, value = entry.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            importer_user=_value("IMPORTER_USER"),
            importer_password=_value("IMPORTER_PASSWORD"),
            session_secret=_value("SESSION_SECRET"),
            cookie_secure=_value("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
            learnhouse_url=_value("LEARNHOUSE_URL", "http://learnhouse"),
            learnhouse_org_id=_value("LEARNHOUSE_ORG_ID", "1"),
            learnhouse_org_slug=_value("LEARNHOUSE_ORG_SLUG", "default"),
            learnhouse_token_file=Path(
                _value("LEARNHOUSE_TOKEN_FILE", "/config/learnhouse-importer.env")
            ),
            import_root=Path(_value("IMPORT_ROOT", "/imports")),
            data_dir=Path(_value("DATA_DIR", "/data")),
            import_workers=max(1, int(_value("IMPORT_WORKERS", "1"))),
            import_source_writable=_value("IMPORT_SOURCE_WRITABLE", "false").lower() in {"1", "true", "yes"},
        )

    def validation_errors(self) -> list[str]:
        required = {
            "IMPORTER_USER": self.importer_user,
            "IMPORTER_PASSWORD": self.importer_password,
            "SESSION_SECRET": self.session_secret,
        }
        return [name for name, value in required.items() if _is_placeholder(value)]

    def ensure_token_file(self) -> None:
        """Create the editable token template once; never write a supplied token."""
        token_file = self.learnhouse_token_file
        try:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            with token_file.open("x", encoding="utf-8") as file:
                file.write(
                    "# Lokale LearnHouse-Ziele; diese Datei niemals committen.\n"
                    "# Ein Ziel: Token, sichtbarer Name sowie ID und Slug der Organisation.\n"
                    "LEARNHOUSE_TOKEN_1=\n"
                    "LEARNHOUSE_ORG_1=\n"
                    "LEARNHOUSE_URL_1=\n"
                    "LEARNHOUSE_ORG_ID_1=\n"
                    "LEARNHOUSE_ORG_SLUG_1=\n"
                    "# Weitere Ziele bei Bedarf fortlaufend nummerieren, z. B. _2.\n"
                )
            try:
                token_file.chmod(0o600)
            except OSError:
                pass
        except FileExistsError:
            return
        except OSError as error:
            raise RuntimeError(
                f"Token-Datei kann nicht angelegt werden: {token_file} ({error})"
            ) from error

    def has_api_token(self) -> bool:
        return bool(self.learnhouse_targets())

    def get_api_token(self) -> str | None:
        targets = self.learnhouse_targets()
        return targets[0].token if targets else None

    def learnhouse_targets(self) -> list["LearnHouseTarget"]:
        """Return configured targets, retaining backwards compatibility with one token."""
        values = self._token_values()
        numbered = sorted(
            {
                int(match.group(1))
                for key, value in values.items()
                if value and (match := re.fullmatch(r"LEARNHOUSE_TOKEN_(\d+)", key))
            }
        )
        targets: list[LearnHouseTarget] = []
        for number in numbered:
            token = values[f"LEARNHOUSE_TOKEN_{number}"]
            url = values.get(f"LEARNHOUSE_URL_{number}") or self.learnhouse_url
            org_id = values.get(f"LEARNHOUSE_ORG_ID_{number}") or self.learnhouse_org_id
            org_slug = values.get(f"LEARNHOUSE_ORG_SLUG_{number}") or self.learnhouse_org_slug
            label = values.get(f"LEARNHOUSE_ORG_{number}") or f"Token {number}"
            targets.append(LearnHouseTarget(str(number), token, label, url, org_id, org_slug))

        # Existing installations retain their one-token configuration unchanged.
        legacy_token = values.get("LEARNHOUSE_API_TOKEN", "")
        if legacy_token and not targets:
            label = values.get("LEARNHOUSE_ORG", "") or "Token 1"
            targets.append(
                LearnHouseTarget(
                    "legacy", legacy_token, label, self.learnhouse_url,
                    self.learnhouse_org_id, self.learnhouse_org_slug,
                )
            )
        return targets


@dataclass(frozen=True)
class LearnHouseTarget:
    """A local target definition. ``token`` must never be returned to the browser."""

    id: str
    token: str
    label: str
    url: str
    org_id: str
    org_slug: str

    def public(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "url": self.url,
            "org_id": self.org_id,
            "org_slug": self.org_slug,
        }


settings = Settings.from_environment()
