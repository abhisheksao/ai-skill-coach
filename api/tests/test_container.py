"""build_services: DI wiring — every service that should share a dependency
(driver, rest client, messages/skills) actually shares the same instance,
not a duplicate; the unconfigured-LLM fallback fails loudly when called."""

import pytest

from skillcoach_api.config import Settings
from skillcoach_api.services.container import Services, _UnconfiguredLlm, build_services

pytestmark = [pytest.mark.foundations, pytest.mark.container]


def make_settings(**overrides) -> Settings:
    defaults: dict = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "service-key",
        "neo4j_uri": "",
        "neo4j_user": "",
        "neo4j_password": "",
        "google_api_key": "",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_build_services_returns_fully_populated_container() -> None:
    services = build_services(make_settings())
    assert isinstance(services, Services)


def test_context_builder_shares_the_same_messages_and_skills_instances() -> None:
    services = build_services(make_settings())
    assert services.context_builder._messages is services.messages
    assert services.context_builder._skills is services.skills


def test_intent_apply_and_skills_share_the_same_graph_driver() -> None:
    services = build_services(make_settings())
    assert services.intent_apply._driver is services.skills._driver


def test_progress_shares_the_same_graph_driver() -> None:
    services = build_services(make_settings())
    assert services.progress._driver is services.skills._driver


def test_cadence_schedule_shares_the_same_rest_client() -> None:
    services = build_services(make_settings())
    assert services.cadence_schedule._rest is services.messages._rest


def test_notifications_shares_the_same_rest_client() -> None:
    services = build_services(make_settings())
    assert services.notifications._rest is services.messages._rest


def test_session_summary_shares_the_same_driver_budget_and_llm() -> None:
    services = build_services(make_settings())
    assert services.session_summary._driver is services.skills._driver
    assert services.session_summary._budget is services.budget
    assert services.session_summary._llm is services.llm


def test_messages_and_profiles_share_the_same_rest_client() -> None:
    services = build_services(make_settings())
    assert services.messages._rest is services.profiles._rest


def test_analytics_shares_the_same_rest_client() -> None:
    services = build_services(make_settings())
    assert services.analytics._rest is services.messages._rest


def test_llm_uses_unconfigured_fallback_when_key_missing() -> None:
    services = build_services(make_settings(google_api_key=""))
    assert isinstance(services.llm._runnable, _UnconfiguredLlm)


async def test_unconfigured_llm_raises_on_invoke() -> None:
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY is not configured"):
        await _UnconfiguredLlm().ainvoke([])
