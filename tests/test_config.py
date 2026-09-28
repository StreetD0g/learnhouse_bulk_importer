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

    assert "LEARNHOUSE_TOKEN_1=\n" in token_file.read_text(encoding="utf-8")
    assert configured.get_api_token() is None
    assert not configured.has_api_token()


def test_token_file_only_checks_presence(tmp_path: Path) -> None:
    token_file = tmp_path / "learnhouse-importer.env"
    token_file.write_text("LEARNHOUSE_API_TOKEN=lh_any_value\n", encoding="utf-8")
    configured = settings(token_file)

    assert configured.get_api_token() == "lh_any_value"
    assert configured.has_api_token()


def test_numbered_targets_keep_tokens_private_and_labels_optional(tmp_path: Path) -> None:
    token_file = tmp_path / "learnhouse-importer.env"
    token_file.write_text(
        "LEARNHOUSE_TOKEN_1=lh_first\n"
        "LEARNHOUSE_ORG_1=Kursakademie\n"
        "LEARNHOUSE_TOKEN_2=lh_second\n"
        "LEARNHOUSE_URL_2=https://other.learnhouse.example\n"
        "LEARNHOUSE_ORG_ID_2=7\n"
        "LEARNHOUSE_ORG_SLUG_2=second-org\n",
        encoding="utf-8",
    )

    targets = settings(token_file).learnhouse_targets()

    assert [target.id for target in targets] == ["1", "2"]
    assert [target.label for target in targets] == ["Kursakademie", "Token 2"]
    assert targets[0].org_id == "1"
    assert targets[0].url == "https://learn.example.com"
    assert targets[1].url == "https://other.learnhouse.example"
    assert targets[1].org_slug == "second-org"
    assert "lh_first" not in str(targets[0].public())
