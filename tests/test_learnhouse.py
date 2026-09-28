from pathlib import Path

import httpx
import pytest

from app.config import LearnHouseTarget, Settings
from app.learnhouse import LearnHouseClient, LearnHouseError


def settings(token_file: Path) -> Settings:
    token_file.write_text("LEARNHOUSE_API_TOKEN=lh_test_token\n", encoding="utf-8")
    return Settings(
        "admin", "password", "session", True, "https://learn.example.com", "1", "default",
        token_file, token_file.parent / "imports", token_file.parent / "data", 1,
    )


def test_connection_uses_bearer_token_without_exposing_it(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "/courses/" in request.url.path:
            return httpx.Response(200, json=[])
        if "/folders/" in request.url.path:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    with LearnHouseClient(settings(tmp_path / "token.env"), transport=httpx.MockTransport(handler)) as client:
        result = client.test_connection()

    assert result["ok"] is True
    assert all(request.headers["authorization"] == "Bearer lh_test_token" for request in requests)


def test_api_error_redacts_token(tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Bearer lh_test_token rejected"})

    with LearnHouseClient(settings(tmp_path / "token.env"), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LearnHouseError) as error:
            client.list_courses()

    assert "lh_test_token" not in str(error.value)
    assert "[REDACTED]" in str(error.value)


def test_selected_target_controls_server_and_organization(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    target = LearnHouseTarget(
        "2", "lh_other_token", "Andere Plattform", "https://other.learnhouse.example", "7", "other-org"
    )
    with LearnHouseClient(
        settings(tmp_path / "token.env"), target=target, transport=httpx.MockTransport(handler)
    ) as client:
        result = client.test_connection()

    assert result["server"] == "https://other.learnhouse.example"
    assert all(request.url.host == "other.learnhouse.example" for request in requests)
    assert any("/courses/org_slug/other-org/" in str(request.url) for request in requests)
    assert any("/folders/org/7/" in str(request.url) for request in requests)
