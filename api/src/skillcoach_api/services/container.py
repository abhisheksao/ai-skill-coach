"""Service container built once at startup; tests replace app.state.services
with fakes."""

from dataclasses import dataclass

import httpx

from coach_core.analytics import AnalyticsService
from coach_core.budget import BudgetGuard
from coach_core.llm_queue import LlmQueue
from coach_core.supabase_rest import SupabaseRest
from skillcoach_api import constants
from skillcoach_api.config import Settings
from skillcoach_api.services.cadence_schedule import CadenceScheduleService
from skillcoach_api.services.context_builder import ContextBuilder
from skillcoach_api.services.graph import GraphService
from skillcoach_api.services.intent_apply import IntentApplyService
from skillcoach_api.services.llm import LlmService, build_production_runnable
from skillcoach_api.services.messages import MessageStore
from skillcoach_api.services.notifications import NotificationsService
from skillcoach_api.services.profiles import ProfileStore
from skillcoach_api.services.progress import ProgressService
from skillcoach_api.services.session_summary import SessionSummaryService
from skillcoach_api.services.skills import SkillsService


@dataclass
class Services:
    budget: BudgetGuard
    llm: LlmService
    messages: MessageStore
    profiles: ProfileStore
    graph: GraphService
    skills: SkillsService
    intent_apply: IntentApplyService
    context_builder: ContextBuilder
    progress: ProgressService
    cadence_schedule: CadenceScheduleService
    notifications: NotificationsService
    session_summary: SessionSummaryService
    analytics: AnalyticsService


class _UnconfiguredLlm:
    """Fails softly when GOOGLE_API_KEY is absent (env not set up yet)."""

    async def ainvoke(self, _messages):
        raise RuntimeError("GOOGLE_API_KEY is not configured")


def build_services(settings: Settings) -> Services:
    http_client = httpx.AsyncClient(timeout=30)
    rest = SupabaseRest(http_client, settings.supabase_url, settings.supabase_service_role_key)

    runnable = (
        build_production_runnable(settings.llm_model, settings.google_api_key)
        if settings.google_api_key
        else _UnconfiguredLlm()
    )

    graph = GraphService.from_settings(settings)
    messages = MessageStore(rest)
    skills = SkillsService(graph.driver)
    progress = ProgressService(graph.driver)
    queue = LlmQueue(
        constants.LLM_MAX_CONCURRENT, constants.LLM_MAX_RPM, constants.LLM_QUEUE_MAX_WAIT_SECONDS
    )
    budget = BudgetGuard(rest, settings.daily_llm_budget, queue)
    llm = LlmService(runnable)
    analytics = AnalyticsService(rest)

    return Services(
        budget=budget,
        llm=llm,
        messages=messages,
        profiles=ProfileStore(rest),
        graph=graph,
        skills=skills,
        intent_apply=IntentApplyService(graph.driver),
        context_builder=ContextBuilder(messages, skills, progress),
        progress=progress,
        cadence_schedule=CadenceScheduleService(rest),
        notifications=NotificationsService(rest, http_client, analytics),
        session_summary=SessionSummaryService(rest, graph.driver, budget, llm, analytics),
        analytics=analytics,
    )
