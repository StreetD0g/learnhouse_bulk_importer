from __future__ import annotations

import os
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
                    "# LearnHouse API token; this file is local and must not be committed.\n"
                    "LEARNHOUSE_API_TOKEN=\n"
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
        try:
            lines = self.learnhouse_token_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#") or "=" not in value:
                continue
            key, token = value.split("=", 1)
            if key.strip() == "LEARNHOUSE_API_TOKEN":
                return bool(token.strip().strip('"').strip("'"))
        return False


settings = Settings.from_environment()
