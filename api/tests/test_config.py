"""Settings: env parsing, defaults with no .env, cors_origin_list edge
cases, and git_sha's AliasChoices precedence (Constitution VI: model/config
identity lives here, never in code)."""

import pytest

from skillcoach_api.config import Settings, get_settings

pytestmark = [pytest.mark.foundations, pytest.mark.config]

_ENV_KEYS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWKS_URL",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "GOOGLE_API_KEY",
    "LLM_MODEL",
    "DAILY_LLM_BUDGET",
    "CORS_ORIGINS",
    "POLICY_URL",
    "GIT_SHA",
    "RENDER_GIT_COMMIT",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_with_no_env_file_or_vars() -> None:
    settings = Settings(_env_file=None)

    assert settings.supabase_url == ""
    assert settings.llm_model == "gemini-flash-lite-latest"
    assert settings.daily_llm_budget == 50
    assert settings.cors_origins == "http://localhost:8081"
    assert settings.git_sha == "dev"


def test_cors_origin_list_splits_strips_and_drops_blanks() -> None:
    settings = Settings(_env_file=None, cors_origins="https://a.com, https://b.com ,,  ")
    assert settings.cors_origin_list == ["https://a.com", "https://b.com"]


def test_cors_origin_list_empty_string_yields_empty_list() -> None:
    assert Settings(_env_file=None, cors_origins="").cors_origin_list == []


def test_git_sha_prefers_git_sha_over_render_git_commit(monkeypatch) -> None:
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "deadbeef")
    assert Settings(_env_file=None).git_sha == "abc123"


def test_git_sha_falls_back_to_render_git_commit(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "deadbeef")
    assert Settings(_env_file=None).git_sha == "deadbeef"


def test_git_sha_defaults_to_dev_when_neither_set() -> None:
    assert Settings(_env_file=None).git_sha == "dev"


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
