from pathlib import Path

from app.config import Settings


def settings(token_file: Path) -> Settings:
    return Settings(
        importer_user="admin",
        importer_password="long-password",
        session_secret="long-session-secret",
        cookie_secure=False,
        learnhouse_url="https://learn.example.com",
        learnhouse_org_id="1",
        learnhouse_org_slug="default",
        learnhouse_token_file=token_file,
        import_root=token_file.parent / "imports",
        data_dir=token_file.parent / "data",
        import_workers=1,
    )


def test_token_file_is_created_without_token(tmp_path: Path) -> None:
    token_file = tmp_path / "config" / "learnhouse-importer.env"
    configured = settings(token_file)

    assert configured.get_api_token() is None
    assert not configured.has_api_token()
    configured.ensure_token_file()

    assert token_file.read_text(encoding="utf-8").endswith("LEARNHOUSE_API_TOKEN=\n")
    assert configured.get_api_token() is None
    assert not configured.has_api_token()


def test_token_file_only_checks_presence(tmp_path: Path) -> None:
    token_file = tmp_path / "learnhouse-importer.env"
    token_file.write_text("LEARNHOUSE_API_TOKEN=lh_any_value\n", encoding="utf-8")
    configured = settings(token_file)

    assert configured.get_api_token() == "lh_any_value"
    assert configured.has_api_token()
