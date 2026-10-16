"""LLM service: single structured call returning ChatTurn {reply, intents[]}
(decision 2026-07-12, option A). Model identity comes from config only
(Constitution VI); every call is budget-gated by the caller (Constitution V).

Two distinct retry loops, per Constitution I:
- Provider-level failures (429/5xx) retry via tenacity with backoff, then
  raise LlmUnavailable (503) — the caller has nothing sensible to persist.
- Output-validation failures retry WITH the error fed back to the model
  (max 2 retries per FR-006); if still invalid, degrade gracefully to a
  reply-only turn (no exception, no intents) rather than a user-visible
  failure. Malformed-output occurrences are logged for telemetry (FR-006).

005/research.md R7: every generate_* method also returns the call's token
usage (`{"prompt_tokens", "output_tokens"}`, or None when unavailable --
e.g. a degraded turn that never reached the provider) so callers can report
it to BudgetGuard.report() for spend visibility. Getting usage requires the
production runnable's structured-output call to run in `include_raw=True`
mode (LangChain only attaches `usage_metadata` to the raw provider message,
never to the parsed Pydantic object) -- which changes parsing failures from
"raised by ainvoke()" to "returned in the raw result's parsing_error field".
`_invoke_once` re-raises that field itself so every existing retry/
degradation rule above is preserved exactly; only the runnable's return
shape changed, not the control flow.
"""

import logging

from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from coach_core.errors import LlmUnavailable
from skillcoach_api.models.chat import ChatTurn
from skillcoach_api.services.context_builder import ConversationContext
from skillcoach_api.services.prompts import (
    build_coaching_prompt,
    build_regenerate_prompt,
    build_summary_prompt,
    build_wizard_prompt,
)

logger = logging.getLogger(__name__)

_VALIDATION_ERRORS = (ValidationError, OutputParserException)
_MAX_VALIDATION_ATTEMPTS = 3  # 1 initial + 2 retries per FR-006
_DEGRADED_REPLY_KEY = "errors.validation"  # i18n key; caller renders it


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int) and (status == 429 or status >= 500):
        return True
    name = type(exc).__name__
    return name in {
        "ResourceExhausted",
        "ServiceUnavailable",
        "InternalServerError",
        "DeadlineExceeded",
    }


def _to_langchain_history(messages: list[dict]) -> list[tuple[str, str]]:
    return [("human" if m["sender"] == "user" else "ai", m["content"]) for m in messages]


UsageInfo = dict[str, int] | None


def _extract_usage(raw_message) -> UsageInfo:
    usage = getattr(raw_message, "usage_metadata", None) if raw_message is not None else None
    if not usage:
        return None
    return {
        "prompt_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


class LlmService:
    """Wraps a LangChain runnable producing {raw, parsed, parsing_error}
    (include_raw=True) so token usage is available alongside ChatTurn. The
    runnable is injected so tests never touch the network; production
    wiring lives in main.py."""

    def __init__(self, runnable, retry_wait_multiplier: float = 1.0) -> None:
        self._runnable = runnable
        self._retry_wait_multiplier = retry_wait_multiplier

    async def _invoke_with_feedback_retry(
        self, system: str, history: list[tuple[str, str]], human_message: str
    ) -> tuple[ChatTurn, UsageInfo]:
        """Provider retry (tenacity) nested inside validation-feedback retry
        (manual loop, max 2, Constitution I). Never raises on validation
        exhaustion — returns a degraded, reply-only ChatTurn instead."""

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=self._retry_wait_multiplier, max=8),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        async def _invoke_once(messages: list[tuple[str, str]]) -> tuple[ChatTurn, UsageInfo]:
            result = await self._runnable.ainvoke(messages)
            if result["parsing_error"] is not None:
                raise result["parsing_error"]
            return result["parsed"], _extract_usage(result.get("raw"))

        messages: list[tuple[str, str]] = [("system", system), *history, ("human", human_message)]

        for attempt in range(_MAX_VALIDATION_ATTEMPTS):
            try:
                return await _invoke_once(messages)
            except _VALIDATION_ERRORS as exc:
                logger.warning(
                    "LLM output failed validation (attempt %d/%d): %s",
                    attempt + 1,
                    _MAX_VALIDATION_ATTEMPTS,
                    exc,
                )
                messages = [
                    *messages,
                    (
                        "human",
                        f"Your previous response did not match the required "
                        f"format ({exc}). Please try again, following the "
                        "schema exactly.",
                    ),
                ]
            except Exception as exc:
                logger.warning("LLM failed after provider retries: %s", type(exc).__name__)
                raise LlmUnavailable() from exc

        logger.warning("Validation retries exhausted; degrading to reply-only turn")
        return ChatTurn(reply=_DEGRADED_REPLY_KEY, intents=[]), None

    async def generate_wizard_turn(
        self, message: str, new_skill_name: str, context: ConversationContext
    ) -> tuple[ChatTurn, UsageInfo]:
        system = build_wizard_prompt(new_skill_name, context)
        return await self._invoke_with_feedback_retry(
            system, _to_langchain_history(context.recent_messages), message
        )

    async def generate_coaching_turn(
        self, message: str, context: ConversationContext
    ) -> tuple[ChatTurn, UsageInfo]:
        system = build_coaching_prompt(context)
        return await self._invoke_with_feedback_retry(
            system, _to_langchain_history(context.recent_messages), message
        )

    async def generate_regeneration(
        self,
        context: ConversationContext,
        reason: str,
        note: str | None,
        force_different: bool = False,
    ) -> tuple[ChatTurn, UsageInfo]:
        system = build_regenerate_prompt(context, reason, note, force_different)
        return await self._invoke_with_feedback_retry(system, [], "Please regenerate the plan.")

    async def generate_session_summary(self, transcript: str) -> tuple[str, UsageInfo]:
        """004, FR-006/FR-007 -- reuses the same ChatTurn schema/runnable
        as every other call (no separate structured-output type or model
        tier provisioned for this one internal call); only `.reply` is
        used, intents are always empty and ignored."""
        system = build_summary_prompt()
        turn, usage = await self._invoke_with_feedback_retry(system, [], transcript)
        return turn.reply, usage


def build_production_runnable(model_name: str, api_key: str):
    """Late import so tests never load the provider SDK. include_raw=True
    (005, research.md R7) so usage_metadata is reachable -- LangChain only
    attaches it to the raw provider message, never the parsed object."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.7)
    return model.with_structured_output(ChatTurn, include_raw=True)
