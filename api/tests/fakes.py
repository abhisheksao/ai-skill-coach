"""Shared fakes for auth and chat-pipeline tests."""

from coach_core.errors import BudgetExceeded
from skillcoach_api.models.chat import ChatTurn


class FakeSigningKey:
    def __init__(self, key) -> None:
        self.key = key


class FakeJwksClient:
    """Stands in for PyJWKClient: always returns the test public key."""

    def __init__(self, public_key) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> FakeSigningKey:
        return FakeSigningKey(self._public_key)


class FakeBudget:
    def __init__(self, over_budget: bool = False, resets_at=None) -> None:
        self.over_budget = over_budget
        self.resets_at = resets_at
        self.calls: list[str] = []
        self.reports: list[tuple[str, dict | None]] = []

    async def acquire(self, user_id: str) -> None:
        self.calls.append(user_id)
        if self.over_budget:
            raise BudgetExceeded(resets_at=self.resets_at)

    async def report(self, user_id: str, usage_metadata: dict | None) -> None:
        self.reports.append((user_id, usage_metadata))


class FakeLlm:
    def __init__(
        self,
        reply: str = "Hello!",
        intents: list | None = None,
        suggested_replies: list[str] | None = None,
        fail: Exception | None = None,
        usage: dict | None = None,
    ) -> None:
        self.reply = reply
        self.intents = intents or []
        self.suggested_replies = suggested_replies or []
        self.fail = fail
        self.usage = usage
        self.calls: list[tuple[str, ...]] = []

    def _turn(self) -> ChatTurn:
        return ChatTurn(
            reply=self.reply, intents=self.intents, suggested_replies=self.suggested_replies
        )

    async def generate_wizard_turn(self, message: str, new_skill_name, context):
        self.calls.append(("wizard", message, new_skill_name, context.language))
        if self.fail:
            raise self.fail
        return self._turn(), self.usage

    async def generate_coaching_turn(self, message: str, context):
        self.calls.append(("coaching", message, context.language))
        if self.fail:
            raise self.fail
        return self._turn(), self.usage

    async def generate_regeneration(self, context, reason, note, force_different=False):
        self.calls.append(("regenerate", reason, note, force_different))
        if self.fail:
            raise self.fail
        return self._turn(), self.usage


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.healthy = True

    async def ensure_user(self, sub: str) -> bool:
        self.calls.append(sub)
        return self.healthy


class FakeProfiles:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    async def upsert(
        self,
        user_id: str,
        display_name: str | None,
        language: str,
        timezone: str,
        voice_replies_enabled: bool = True,
    ) -> dict:
        row = {
            "user_id": user_id,
            "display_name": display_name,
            "language": language,
            "timezone": timezone,
            "consent_at": "2026-07-12T00:00:00+00:00",
            "voice_replies_enabled": voice_replies_enabled,
        }
        self.upserts.append(row)
        return row


class FakeMessages:
    def __init__(self, language: str = "en", recent: list[dict] | None = None) -> None:
        self.language = language
        self.recent = recent or []
        self.turn_count = 0
        self.inserted: list[dict] = []

    async def insert_turn(
        self,
        user_id: str,
        session_id: str,
        skill_id: str | None,
        user_text: str,
        assistant_text: str,
        modality: str = "chat",
    ) -> None:
        self.inserted.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "skill_id": skill_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "modality": modality,
            }
        )

    async def profile_language(self, user_id: str) -> str:
        return self.language

    async def recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        return self.recent

    async def count_user_turns(self, session_id: str) -> int:
        return self.turn_count


class FakeProgress:
    """Not-behind by default (no gap description) -- shared across
    chat-pipeline test files that need ContextBuilder wired but don't
    care about cadence-gap specifics themselves (those get their own
    dedicated coverage in test_context_builder.py)."""

    def __init__(self, skill_progress=None) -> None:
        self._skill_progress = skill_progress
        self.calls: list[tuple] = []

    async def compute(self, user_id: str, skill_id: str, timezone: str):
        from skillcoach_api.services.progress import SkillProgress

        self.calls.append((user_id, skill_id, timezone))
        return self._skill_progress or SkillProgress(
            skill_id=skill_id, completed_steps=[], total_steps=0, streak_days=0, steps=[]
        )


class FakeContextBuilder:
    def __init__(self, skill=None, language: str = "en", recent=None, turn_count: int = 0) -> None:
        self.skill = skill
        self.language = language
        self.recent = recent or []
        self.turn_count = turn_count
        self.calls: list[tuple] = []

    async def build(self, user_id: str, skill_id: str | None, session_id: str):
        from skillcoach_api.services.context_builder import ConversationContext

        self.calls.append((user_id, skill_id, session_id))
        return ConversationContext(
            language=self.language,
            skill=self.skill,
            recent_messages=self.recent,
            user_turn_count=self.turn_count,
        )


class FakeCadenceSchedule:
    def __init__(self) -> None:
        self.synced: list[tuple] = []

    async def sync(self, user_id: str, skill_id: str, steps: list) -> None:
        self.synced.append((user_id, skill_id, steps))


class FakeAnalytics:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, str | None, dict | None]] = []

    async def emit(
        self, event_type: str, user_sub: str | None, properties: dict | None = None
    ) -> None:
        self.emitted.append((event_type, user_sub, properties))


class FakeIntentApply:
    def __init__(self, created_skill_id: str | None = None) -> None:
        self.created_skill_id = created_skill_id
        self.applied: list = []

    async def apply_intents(
        self,
        intents: list,
        user_id: str,
        skill_id: str | None = None,
        valid_step_orders: set[int] | None = None,
        source: str = "conversation",
    ):
        from skillcoach_api.services.intent_apply import ApplyResult

        self.applied.append((intents, user_id, skill_id, valid_step_orders, source))
        return ApplyResult(created_skill_id=self.created_skill_id)
