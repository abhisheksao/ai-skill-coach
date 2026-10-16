"""MessageStore: server-side stamping of user_id/modality/skill scope, plus
negative paths: a REST failure must propagate (never be swallowed), and a
profile row missing its `language` key raises rather than silently
defaulting -- documenting current behavior explicitly rather than leaving
it an untested assumption."""

import pytest

from skillcoach_api.services.messages import MessageStore

pytestmark = [pytest.mark.foundations, pytest.mark.messages]


class FakeRest:
    def __init__(
        self, profile_row: dict | None = None, many_rows: list[dict] | None = None
    ) -> None:
        self.inserts: list[tuple[str, list[dict]]] = []
        self.many_calls: list[tuple] = []
        self._profile_row = profile_row
        self._many_rows = many_rows or []

    async def insert(self, table: str, rows: list[dict]) -> None:
        self.inserts.append((table, rows))

    async def select_one(self, table: str, filters: dict, columns: str) -> dict | None:
        return self._profile_row

    async def select_many(
        self, table: str, filters: dict, columns: str, order: str | None = None, limit=None
    ) -> list[dict]:
        self.many_calls.append((table, filters, columns, order, limit))
        return self._many_rows


async def test_insert_turn_writes_both_rows_stamped() -> None:
    rest = FakeRest()
    store = MessageStore(rest)
    await store.insert_turn("user-1", "session-1", None, "hi coach", "hello!")

    table, rows = rest.inserts[0]
    assert table == "messages"
    assert len(rows) == 2
    for row in rows:
        assert row["user_id"] == "user-1"
        assert row["session_id"] == "session-1"
        assert row["skill_id"] is None
        assert row["modality"] == "chat"
    assert rows[0]["sender"] == "user" and rows[0]["content"] == "hi coach"
    assert rows[1]["sender"] == "assistant" and rows[1]["content"] == "hello!"


async def test_insert_turn_stamps_skill_id_once_a_skill_exists() -> None:
    rest = FakeRest()
    store = MessageStore(rest)
    await store.insert_turn("user-1", "session-1", "skill-1", "let's continue", "sure!")

    _, rows = rest.inserts[0]
    assert all(row["skill_id"] == "skill-1" for row in rows)


async def test_profile_language_falls_back_to_english() -> None:
    assert await MessageStore(FakeRest(None)).profile_language("u") == "en"
    assert await MessageStore(FakeRest({"language": "de"})).profile_language("u") == "de"


async def test_recent_messages_reverses_desc_rows_to_chronological() -> None:
    rest = FakeRest(
        many_rows=[{"sender": "assistant", "content": "b"}, {"sender": "user", "content": "a"}]
    )
    messages = await MessageStore(rest).recent_messages("session-1")

    assert [m["content"] for m in messages] == ["a", "b"]
    table, filters, _, order, limit = rest.many_calls[0]
    assert table == "messages"
    assert filters == {"session_id": "session-1"}
    assert order == "created_at.desc"
    assert limit == 20


async def test_count_user_turns_filters_by_sender() -> None:
    rest = FakeRest(many_rows=[{"id": "1"}, {"id": "2"}])
    count = await MessageStore(rest).count_user_turns("session-1")

    assert count == 2
    _, filters, _, _, _ = rest.many_calls[0]
    assert filters == {"session_id": "session-1", "sender": "user"}


async def test_profile_language_raises_keyerror_if_row_missing_language_field() -> None:
    """Documents current behavior: a profile row without a `language` key
    (shouldn't happen given the DB schema, but nothing here guards it)
    raises KeyError rather than silently falling back to English."""
    with pytest.raises(KeyError):
        await MessageStore(FakeRest({"other_field": "x"})).profile_language("u1")


class FailingRest:
    async def insert(self, table: str, rows: list[dict]) -> None:
        raise RuntimeError("supabase down")

    async def select_one(self, table: str, filters: dict, columns: str) -> dict | None:
        raise RuntimeError("supabase down")

    async def select_many(
        self, table: str, filters: dict, columns: str, order: str | None = None, limit=None
    ) -> list[dict]:
        raise RuntimeError("supabase down")


async def test_insert_turn_propagates_a_rest_failure() -> None:
    with pytest.raises(RuntimeError, match="supabase down"):
        await MessageStore(FailingRest()).insert_turn("u1", "s1", None, "hi", "hello")


async def test_profile_language_propagates_a_rest_failure() -> None:
    with pytest.raises(RuntimeError, match="supabase down"):
        await MessageStore(FailingRest()).profile_language("u1")


async def test_recent_messages_propagates_a_rest_failure() -> None:
    with pytest.raises(RuntimeError, match="supabase down"):
        await MessageStore(FailingRest()).recent_messages("s1")


async def test_count_user_turns_propagates_a_rest_failure() -> None:
    with pytest.raises(RuntimeError, match="supabase down"):
        await MessageStore(FailingRest()).count_user_turns("s1")
