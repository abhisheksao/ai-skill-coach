"""Settings via environment (.env locally, host secrets in deploys).

Constitution VI: model identity and tier live here, never in code.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwks_url: str = ""

    # Neo4j Aura
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""

    # LLM (Constitution V/VI)
    google_api_key: str = ""
    llm_model: str = "gemini-flash-lite-latest"
    daily_llm_budget: int = 50

    # App
    cors_origins: str = "http://localhost:8081"  # comma-separated
    policy_url: str = "https://example.com/skillcoach-policy"
    # Shared secret for the two internal cron-triggered endpoints (004,
    # research.md R1) -- there's no authenticated user for a pg_cron/pg_net
    # trigger. Empty by default so an unconfigured deploy fails closed.
    internal_secret: str = ""
    # Render injects RENDER_GIT_COMMIT automatically; /health reports it.
    git_sha: str = Field(
        default="dev", validation_alias=AliasChoices("GIT_SHA", "RENDER_GIT_COMMIT")
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
