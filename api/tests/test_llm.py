"""LlmService: wizard/coaching/regenerate prompts, provider retry/backoff
-> 503, validation-failure retry-with-feedback -> graceful degradation
(Constitution I, FR-006), and token-usage passthrough (005, research.md R7)."""

from datetime import date
from types import SimpleNamespace

import pytest
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from coach_core.errors import LlmUnavailable
from skillcoach_api.models.chat import ChatTurn
from skillcoach_api.models.skills import GoalDetail, PlanDetail, SkillDetail, StepDetail
from skillcoach_api.services.context_builder import ConversationContext
from skillcoach_api.services.llm import LlmService

pytestmark = [pytest.mark.wizard_plan, pytest.mark.llm]


def _raw_message(prompt_tokens: int = 0, output_tokens: int = 0):
    if prompt_tokens == 0 and output_tokens == 0:
        return SimpleNamespace(usage_metadata=None)
    return SimpleNamespace(
        usage_metadata={"input_tokens": prompt_tokens, "output_tokens": output_tokens}
    )


class FakeRunnable:
    """Mimics with_structured_output(ChatTurn, include_raw=True)'s
    {raw, parsed, parsing_error} return shape. Provider-level failures
    (429/5xx) still raise directly from ainvoke -- include_raw only changes
    how PARSING failures surface (returned, not raised)."""

    def __init__(self, results: list) -> None:
        self._results = iter(results)
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, ValidationError | OutputParserException):
            return {"raw": None, "parsed": None, "parsing_error": result}
        turn, raw = result if isinstance(result, tuple) else (result, _raw_message())
        return {"raw": raw, "parsed": turn, "parsing_error": None}


class Retryable(Exception):
    status_code = 429


class NotRetryable(Exception):
    pass


def _make_validation_error() -> ValidationError:
    try:
        ChatTurn.model_validate({"reply": 123, "intents": "not-a-list"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


NEW_SKILL_CONTEXT = ConversationContext(
    language="hi", skill=None, recent_messages=[], user_turn_count=0
)

EXISTING_SKILL = SkillDetail(
    id="skill-1",
    name="Swimming",
    goal=GoalDetail(statement="Swim 1km", target_date=date(2026, 12, 1)),
    plan=PlanDetail(
        id="plan-1",
        generation=0,
        steps=[StepDetail(order=1, description="Float and glide", cadence_per_week=3)],
    ),
)
SKILL_CONTEXT = ConversationContext(
    language="en", skill=EXISTING_SKILL, recent_messages=[], user_turn_count=2
)


async def test_wizard_turn_language_in_system_prompt() -> None:
    runnable = FakeRunnable([ChatTurn(reply="नमस्ते!", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    turn, _usage = await service.generate_wizard_turn("hello", "Swimming", NEW_SKILL_CONTEXT)

    assert turn.reply == "नमस्ते!"
    system_message = runnable.calls[0][0][1]
    assert "Hindi" in system_message
    assert "Swimming" in system_message


async def test_wizard_prompt_states_todays_date_and_requires_future_target() -> None:
    import datetime

    runnable = FakeRunnable([ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    await service.generate_wizard_turn("hello", "Swimming", NEW_SKILL_CONTEXT)

    system_message = runnable.calls[0][0][1]
    assert datetime.date.today().isoformat() in system_message
    assert "MUST be in the future" in system_message


async def test_wizard_prompt_instructs_suggested_replies_for_closed_set_fields() -> None:
    runnable = FakeRunnable([ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    await service.generate_wizard_turn("hello", "Swimming", NEW_SKILL_CONTEXT)

    system_message = runnable.calls[0][0][1]
    assert "suggested_replies" in system_message
    assert "current level" in system_message.lower()
    assert "weekly practice frequency" in system_message.lower()


async def test_coaching_turn_includes_skill_context() -> None:
    runnable = FakeRunnable([ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    await service.generate_coaching_turn("how's it going", SKILL_CONTEXT)

    system_message = runnable.calls[0][0][1]
    assert "Swimming" in system_message
    assert "Swim 1km" in system_message


async def test_regeneration_includes_reason_and_note() -> None:
    runnable = FakeRunnable([ChatTurn(reply="Here's a gentler plan!", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    await service.generate_regeneration(
        SKILL_CONTEXT, "too_much", "too intense", force_different=False
    )

    system_message = runnable.calls[0][0][1]
    assert "too_much" in system_message
    assert "too intense" in system_message


async def test_regeneration_force_different_flag_reaches_prompt() -> None:
    runnable = FakeRunnable([ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    await service.generate_regeneration(SKILL_CONTEXT, "too_easy", None, force_different=True)

    system_message = runnable.calls[0][0][1]
    assert "MEANINGFULLY DIFFERENT" in system_message


async def test_provider_retries_then_succeeds() -> None:
    runnable = FakeRunnable([Retryable(), Retryable(), ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    turn, _usage = await service.generate_coaching_turn("hello", SKILL_CONTEXT)
    assert turn.reply == "ok"
    assert len(runnable.calls) == 3


async def test_provider_retries_exhausted_raise_llm_unavailable() -> None:
    runnable = FakeRunnable([Retryable(), Retryable(), Retryable()])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    with pytest.raises(LlmUnavailable):
        await service.generate_coaching_turn("hello", SKILL_CONTEXT)
    assert len(runnable.calls) == 3


async def test_non_retryable_provider_error_fails_immediately() -> None:
    runnable = FakeRunnable([NotRetryable()])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    with pytest.raises(LlmUnavailable):
        await service.generate_coaching_turn("hello", SKILL_CONTEXT)
    assert len(runnable.calls) == 1


async def test_validation_error_retries_with_feedback_then_succeeds() -> None:
    """Constitution I / FR-006: a validation failure must NOT immediately
    become LlmUnavailable — it retries with the error fed back, up to 2
    times, before giving up."""
    runnable = FakeRunnable([_make_validation_error(), ChatTurn(reply="fixed!", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    turn, _usage = await service.generate_coaching_turn("hello", SKILL_CONTEXT)

    assert turn.reply == "fixed!"
    assert len(runnable.calls) == 2
    # second attempt's message list grew with the feedback message
    assert len(runnable.calls[1]) > len(runnable.calls[0])


async def test_validation_error_exhausted_degrades_gracefully() -> None:
    """After 2 retries (3 total attempts) still invalid -> no exception,
    reply-only degraded turn, never a 503 for a validation problem."""
    runnable = FakeRunnable(
        [_make_validation_error(), _make_validation_error(), _make_validation_error()]
    )
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    turn, usage = await service.generate_coaching_turn("hello", SKILL_CONTEXT)

    assert turn.intents == []
    assert len(runnable.calls) == 3
    assert usage is None  # never reached a real provider response to meter


async def test_output_parser_exception_also_triggers_feedback_retry() -> None:
    runnable = FakeRunnable([OutputParserException("bad json"), ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    turn, _usage = await service.generate_coaching_turn("hello", SKILL_CONTEXT)
    assert turn.reply == "ok"


async def test_usage_metadata_passed_through_from_raw_message() -> None:
    runnable = FakeRunnable(
        [(ChatTurn(reply="ok", intents=[]), _raw_message(prompt_tokens=120, output_tokens=40))]
    )
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    _turn, usage = await service.generate_coaching_turn("hello", SKILL_CONTEXT)
    assert usage == {"prompt_tokens": 120, "output_tokens": 40}


async def test_usage_metadata_none_when_raw_message_has_none() -> None:
    runnable = FakeRunnable([ChatTurn(reply="ok", intents=[])])
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    _turn, usage = await service.generate_coaching_turn("hello", SKILL_CONTEXT)
    assert usage is None


async def test_session_summary_returns_reply_and_usage() -> None:
    runnable = FakeRunnable(
        [
            (
                ChatTurn(reply="Talked about drills.", intents=[]),
                _raw_message(prompt_tokens=200, output_tokens=30),
            )
        ]
    )
    service = LlmService(runnable, retry_wait_multiplier=0.001)
    summary, usage = await service.generate_session_summary("user: hi\nassistant: hello")
    assert summary == "Talked about drills."
    assert usage == {"prompt_tokens": 200, "output_tokens": 30}
