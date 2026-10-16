"""NotificationsService: push-token lifecycle, frequency cap (max
NOTIFICATION_MAX_PER_SKILL_PER_DAY/_PER_WEEK), quiet-hours gating, and
delivery-outcome logging (FR-010, FR-013)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from skillcoach_api import constants
from skillcoach_api import internal_auth as internal_auth_module
from skillcoach_api.main import create_app
from skillcoach_api.services.notifications import NotificationsService
from skillcoach_api.services.progress import SkillProgress, StepProgress
from tests.fakes import FakeAnalytics

pytestmark = [pytest.mark.progress_notifications, pytest.mark.notifications]


class FakeRest:
    """Filters by table + eq filters + a `sent_at gte.` raw_filter well
    enough to drive realistic frequency-cap scenarios without a real DB."""

    def __init__(self) -> None:
        self.inserts: list[tuple] = []
        self.updates: list[tuple] = []
        self.select_many_calls: list[tuple] = []
        self._push_tokens: list[dict] = []
        self._notifications: list[dict] = []

    def seed_tokens(self, user_id: str, tokens: list[str]) -> None:
        for token in tokens:
            self._push_tokens.append(
                {"user_id": user_id, "token": token, "platform": "ios", "revoked_at": None}
            )

    def seed_sent(self, user_id: str, skill_id: str, sent_at: datetime) -> None:
        self._notifications.append(
            {
                "user_id": user_id,
                "skill_id": skill_id,
                "delivery_status": "sent",
                "sent_at": sent_at.isoformat(),
            }
        )

    async def select_one(self, table, filters, columns) -> dict | None:
        if table == "push_tokens":
            for row in self._push_tokens:
                if all(row.get(k) == v for k, v in filters.items()):
                    return row
        return None

    async def select_many(
        self, table, filters, columns, order=None, limit=None, raw_filters=None
    ) -> list[dict]:
        self.select_many_calls.append((table, filters, columns, raw_filters))
        if table == "push_tokens":
            rows = [r for r in self._push_tokens if all(r.get(k) == v for k, v in filters.items())]
            if raw_filters and raw_filters.get("revoked_at") == "is.null":
                rows = [r for r in rows if r.get("revoked_at") is None]
            return rows
        if table == "notifications":
            rows = [
                n for n in self._notifications if all(n.get(k) == v for k, v in filters.items())
            ]
            if raw_filters and "sent_at" in raw_filters:
                threshold = raw_filters["sent_at"].removeprefix("gte.")
                rows = [n for n in rows if n["sent_at"] >= threshold]
            return rows
        return []

    async def insert(self, table, rows) -> None:
        self.inserts.append((table, rows))
        if table == "notifications":
            for row in rows:
                self._notifications.append({**row, "sent_at": datetime.now(UTC).isoformat()})
        elif table == "push_tokens":
            self._push_tokens.extend(rows)

    async def update(self, table, filters, patch) -> None:
        self.updates.append((table, filters, patch))
        if table == "push_tokens":
            for row in self._push_tokens:
                if all(row.get(k) == v for k, v in filters.items()):
                    row.update(patch)


def make_http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok_push_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"status": "ok"}]})


DAYTIME = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)  # noon UTC


# --------------------------------------------------------------- push tokens


async def test_register_token_inserts_when_none_exists() -> None:
    rest = FakeRest()
    await NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics()).register_token(
        "user-1", "ExponentPushToken[abc]", "ios"
    )
    table, rows = rest.inserts[0]
    assert table == "push_tokens"
    assert rows[0]["token"] == "ExponentPushToken[abc]"
    assert rows[0]["revoked_at"] is None
    assert not rest.updates


async def test_register_token_reactivates_existing_row_instead_of_inserting() -> None:
    """Re-registering the same (user, token) pair -- e.g. the device
    re-registers on every app launch (use-push-notifications.ts) -- must
    update the existing row, not attempt a second insert. push_tokens'
    uniqueness is a PARTIAL index (WHERE revoked_at IS NULL), which a plain
    `ON CONFLICT (user_id, token)` upsert can't target (Postgres error
    42P10, found via live device testing 2026-07-18) -- this proves the
    fix (select-then-branch) never takes that path at all, on a revoked
    row too (the exact "device re-registers after a prior revoke" case)."""
    rest = FakeRest()
    rest._push_tokens.append(
        {
            "user_id": "user-1",
            "token": "ExponentPushToken[abc]",
            "platform": "ios",
            "revoked_at": "2026-07-01T00:00:00Z",
        }
    )
    await NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics()).register_token(
        "user-1", "ExponentPushToken[abc]", "android"
    )
    assert not rest.inserts
    table, filters, patch = rest.updates[0]
    assert table == "push_tokens"
    assert filters == {"user_id": "user-1", "token": "ExponentPushToken[abc]"}
    assert patch == {"platform": "android", "revoked_at": None}
    assert rest._push_tokens[0]["revoked_at"] is None


async def test_revoke_token_sets_revoked_at() -> None:
    rest = FakeRest()
    await NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics()).revoke_token(
        "user-1", "ExponentPushToken[abc]"
    )
    table, filters, patch = rest.updates[0]
    assert table == "push_tokens"
    assert filters == {"user_id": "user-1", "token": "ExponentPushToken[abc]"}
    assert "revoked_at" in patch


async def test_active_tokens_reads_only_non_revoked_rows() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1", "tok-2"])
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())
    tokens = await service.active_tokens("user-1")
    assert tokens == ["tok-1", "tok-2"]
    _, _, _, raw_filters = rest.select_many_calls[0]
    assert raw_filters == {"revoked_at": "is.null"}


# ------------------------------------------------------------------ gating


def test_is_daytime_true_within_quiet_hours_window() -> None:
    service = NotificationsService(FakeRest(), make_http(ok_push_handler), FakeAnalytics())
    noon = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    assert service.is_daytime(noon, "UTC") is True


def test_is_daytime_false_before_quiet_hours_start() -> None:
    service = NotificationsService(FakeRest(), make_http(ok_push_handler), FakeAnalytics())
    early = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
    assert service.is_daytime(early, "UTC") is False


def test_is_daytime_false_after_quiet_hours_end() -> None:
    service = NotificationsService(FakeRest(), make_http(ok_push_handler), FakeAnalytics())
    late = datetime(2026, 7, 20, 21, 0, tzinfo=UTC)
    assert service.is_daytime(late, "UTC") is False


def test_is_daytime_respects_the_users_own_timezone_not_utc() -> None:
    """21:00 UTC is 14:00 in America/Los_Angeles (UTC-7 in July) -- well
    within daytime there even though it's past quiet hours in UTC."""
    service = NotificationsService(FakeRest(), make_http(ok_push_handler), FakeAnalytics())
    late_utc = datetime(2026, 7, 20, 21, 0, tzinfo=UTC)
    assert service.is_daytime(late_utc, "America/Los_Angeles") is True


async def test_within_frequency_cap_true_with_no_prior_sends() -> None:
    service = NotificationsService(FakeRest(), make_http(ok_push_handler), FakeAnalytics())
    assert await service.within_frequency_cap("user-1", "skill-1", DAYTIME) is True


async def test_within_frequency_cap_false_when_daily_per_skill_cap_reached() -> None:
    rest = FakeRest()
    rest.seed_sent("user-1", "skill-1", DAYTIME - timedelta(hours=2))
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())
    assert await service.within_frequency_cap("user-1", "skill-1", DAYTIME) is False
    # A DIFFERENT skill for the same user is unaffected by skill-1's cap.
    assert await service.within_frequency_cap("user-1", "skill-2", DAYTIME) is True


async def test_within_frequency_cap_false_when_weekly_per_user_cap_reached() -> None:
    rest = FakeRest()
    for i in range(constants.NOTIFICATION_MAX_PER_WEEK):
        rest.seed_sent("user-1", f"skill-{i}", DAYTIME - timedelta(days=i + 1))
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())
    # A skill with zero sends today still hits the user-wide weekly cap.
    assert await service.within_frequency_cap("user-1", "skill-new", DAYTIME) is False


async def test_within_frequency_cap_ignores_sends_older_than_the_windows() -> None:
    rest = FakeRest()
    rest.seed_sent("user-1", "skill-1", DAYTIME - timedelta(days=10))
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())
    assert await service.within_frequency_cap("user-1", "skill-1", DAYTIME) is True


# ------------------------------------------------------- send_cadence_nudge


async def test_send_cadence_nudge_skips_outside_daytime_and_logs_nothing() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    night = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)
    status = await NotificationsService(
        rest, make_http(ok_push_handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", night, "en", "Kick drills", 5
    )
    assert status is None
    assert rest.inserts == []


async def test_send_cadence_nudge_skips_over_frequency_cap_and_logs_nothing() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    rest.seed_sent("user-1", "skill-1", DAYTIME - timedelta(hours=1))
    status = await NotificationsService(
        rest, make_http(ok_push_handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )
    assert status is None
    assert (
        len(rest.inserts) == 0
    )  # the earlier seeded send wasn't via insert(), only new ones count


async def test_send_cadence_nudge_logs_skipped_no_token_when_none_active() -> None:
    rest = FakeRest()  # no tokens seeded
    status = await NotificationsService(
        rest, make_http(ok_push_handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )
    assert status == "skipped_no_token"
    table, rows = rest.inserts[0]
    assert table == "notifications"
    assert rows[0]["delivery_status"] == "skipped_no_token"
    assert "Kick drills" in rows[0]["gap_description"]


async def test_send_cadence_nudge_sends_and_logs_on_success() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json={"data": [{"status": "ok"}]})

    status = await NotificationsService(
        rest, make_http(handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )
    assert status == "sent"
    assert b"Kick drills" in captured["body"]
    _, rows = rest.inserts[0]
    assert rows[0]["delivery_status"] == "sent"


async def test_send_cadence_nudge_uses_the_recipients_language_not_english() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"data": [{"status": "ok"}]})

    await NotificationsService(rest, make_http(handler), FakeAnalytics()).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "hi", "Kick drills", 5
    )
    assert "जांच" in captured["body"]  # Hindi copy, not the English template
    assert "Time for a check-in" not in captured["body"]


async def test_send_cadence_nudge_logs_skipped_permission_denied_on_dead_token() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "message": "...",
                        "details": {"error": "DeviceNotRegistered"},
                    }
                ]
            },
        )

    status = await NotificationsService(
        rest, make_http(handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )
    assert status == "skipped_permission_denied"


async def test_send_cadence_nudge_reports_sent_when_one_of_several_tokens_succeeds() -> None:
    """A user can have multiple tokens (one per device); a dead/malformed
    one must never mask a genuine delivery to another (found live,
    2026-07-18 -- a stray malformed token registered alongside a valid one
    made an actual successful send report as skipped_permission_denied)."""
    rest = FakeRest()
    rest.seed_tokens("user-1", ["dead-tok", "live-tok"])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "message": "...",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                    {"status": "ok"},
                ]
            },
        )

    status = await NotificationsService(
        rest, make_http(handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )
    assert status == "sent"


async def test_send_cadence_nudge_logs_failed_on_http_error() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    status = await NotificationsService(
        rest, make_http(handler), FakeAnalytics()
    ).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )
    assert status == "failed"
    _, rows = rest.inserts[0]
    assert rows[0]["delivery_status"] == "failed"


async def test_push_sent_analytics_emitted_on_success() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    analytics = FakeAnalytics()

    await NotificationsService(rest, make_http(ok_push_handler), analytics).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )

    assert ("push_sent", "user-1", {"skill_id": "skill-1"}) in analytics.emitted


async def test_push_failed_analytics_emitted_on_http_error() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    analytics = FakeAnalytics()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    await NotificationsService(rest, make_http(handler), analytics).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )

    assert ("push_failed", "user-1", {"skill_id": "skill-1", "reason": "provider_error"}) in (
        analytics.emitted
    )


async def test_no_push_analytics_event_when_skipped_no_token() -> None:
    """skipped_* outcomes are pre-send/no-token gates, not delivery
    attempts -- neither push_sent nor push_failed applies (data-model.md's
    vocabulary has no "skipped" event)."""
    rest = FakeRest()  # no tokens seeded
    analytics = FakeAnalytics()

    await NotificationsService(rest, make_http(ok_push_handler), analytics).send_cadence_nudge(
        "user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5
    )

    assert analytics.emitted == []


async def test_analytics_failure_never_blocks_the_delivery_log() -> None:
    """005, plan.md note 5: a real AnalyticsService wired to a rest client
    that fails ONLY for analytics_events must not stop the notifications
    delivery-log row from being written."""
    from coach_core.analytics import AnalyticsService

    class FailingAnalyticsRest(FakeRest):
        async def insert(self, table, rows) -> None:
            if table == "analytics_events":
                raise RuntimeError("PostgREST unreachable")
            await super().insert(table, rows)

    rest = FailingAnalyticsRest()
    rest.seed_tokens("user-1", ["tok-1"])

    status = await NotificationsService(
        rest, make_http(ok_push_handler), AnalyticsService(rest)
    ).send_cadence_nudge("user-1", "skill-1", "UTC", DAYTIME, "en", "Kick drills", 5)

    assert status == "sent"
    _, rows = rest.inserts[-1]
    assert rows[0]["delivery_status"] == "sent"


# ------------------------------------------------------------- Edge Case


async def test_three_skills_behind_at_once_each_get_exactly_one_notification() -> None:
    """Edge Case: multiple skills behind simultaneously -- each is gated
    and logged INDEPENDENTLY (own per-skill-per-day cap), never suppressed
    into nothing nor combined into one mega-send; the shared per-user
    weekly cap still bounds the total across all of them."""
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())

    statuses = [
        await service.send_cadence_nudge("user-1", skill_id, "UTC", DAYTIME, "en", "Some step", 5)
        for skill_id in ("skill-1", "skill-2", "skill-3")
    ]

    assert statuses == ["sent", "sent", "sent"]
    sent_skill_ids = {row["skill_id"] for _, rows in rest.inserts for row in rows}
    assert sent_skill_ids == {"skill-1", "skill-2", "skill-3"}


async def test_a_fourth_skill_behind_the_same_week_hits_the_weekly_cap() -> None:
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())

    skill_ids = [f"skill-{i}" for i in range(constants.NOTIFICATION_MAX_PER_WEEK + 1)]
    statuses = [
        await service.send_cadence_nudge("user-1", skill_id, "UTC", DAYTIME, "en", "Some step", 5)
        for skill_id in skill_ids
    ]

    assert (
        statuses[: constants.NOTIFICATION_MAX_PER_WEEK]
        == ["sent"] * constants.NOTIFICATION_MAX_PER_WEEK
    )
    assert statuses[-1] is None  # the (cap + 1)th skill this week gets nothing


async def test_multi_week_simulation_never_exceeds_the_frequency_cap() -> None:
    """SC-004: 'no user receives notifications exceeding the agreed
    frequency cap ... verified over a simulated multi-week run.' Simulates
    a single behind-cadence skill going through the scan once a day for 3
    weeks -- every 7-day trailing window's sent count must stay within
    NOTIFICATION_MAX_PER_WEEK, and every single day's count within
    NOTIFICATION_MAX_PER_SKILL_PER_DAY (trivial here since called once/day,
    but asserted anyway as a real invariant, not an assumption)."""
    rest = FakeRest()
    rest.seed_tokens("user-1", ["tok-1"])
    service = NotificationsService(rest, make_http(ok_push_handler), FakeAnalytics())

    start = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    daily_statuses = []
    for day in range(21):  # 3 weeks
        now = start + timedelta(days=day)
        status = await service.send_cadence_nudge(
            "user-1", "skill-1", "UTC", now, "en", "Kick drills", 5
        )
        daily_statuses.append((now, status))

    # Per-day cap: never more than one 'sent' logged for THIS calendar day
    # (only one call/day happens here, but confirm the log reflects it).
    sent_at_by_day = [now for now, status in daily_statuses if status == "sent"]
    for day_time in sent_at_by_day:
        same_day_sent = [t for t in sent_at_by_day if t.date() == day_time.date()]
        assert len(same_day_sent) <= constants.NOTIFICATION_MAX_PER_SKILL_PER_DAY

    # Per-week cap: every rolling 7-day window has at most
    # NOTIFICATION_MAX_PER_WEEK sends.
    for window_start in range(21 - 6):
        window_end = start + timedelta(days=window_start + 7)
        window_start_dt = start + timedelta(days=window_start)
        in_window = [t for t in sent_at_by_day if window_start_dt <= t < window_end]
        assert len(in_window) <= constants.NOTIFICATION_MAX_PER_WEEK

    # And it's not a degenerate all-skipped run -- real sends did happen.
    assert len(sent_at_by_day) > 0


async def test_on_cadence_skill_never_reaches_send_cadence_nudge_via_the_scan() -> None:
    """The other half of SC-004/the multi-week guarantee: an on-cadence
    skill must get zero notifications, which is enforced upstream of
    NotificationsService entirely -- routes/internal.py's scan only calls
    send_cadence_nudge for a skill with a behind_cadence step at all. This
    documents that boundary directly against the real route."""

    class FakeCadenceScheduleAllRows:
        async def all_rows(self):
            return [{"user_id": "user-1", "skill_id": "skill-1"}]

    class FakeSkillsOnCadence:
        async def get_skill(self, _user_id, _skill_id):
            return SimpleNamespace(
                name="Swimming",
                plan=SimpleNamespace(
                    steps=[SimpleNamespace(order=1, description="Float and glide")]
                ),
            )

    class FakeMessagesOnCadence:
        async def profile_timezone(self, _user_id):
            return "UTC"

        async def profile_language(self, _user_id):
            return "en"

    class FakeProgressOnCadence:
        async def compute(self, _user_id, skill_id, _timezone):
            return SkillProgress(
                skill_id=skill_id,
                completed_steps=[],
                total_steps=1,
                streak_days=4,
                steps=[
                    StepProgress(
                        order=1,
                        completed=False,
                        behind_cadence=False,  # on cadence -- nothing to nudge
                        last_checkin_at=None,
                        anchor_at=datetime.now(UTC),
                    )
                ],
            )

    class SpyNotifications:
        def __init__(self) -> None:
            self.calls: list = []

        async def send_cadence_nudge(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return "sent"

    spy = SpyNotifications()
    app = create_app()
    app.state.services = SimpleNamespace(
        cadence_schedule=FakeCadenceScheduleAllRows(),
        skills=FakeSkillsOnCadence(),
        messages=FakeMessagesOnCadence(),
        progress=FakeProgressOnCadence(),
        notifications=spy,
    )
    secret = "test-secret-" + str(uuid.uuid4())
    original_get_settings = internal_auth_module.get_settings
    internal_auth_module.get_settings = lambda: SimpleNamespace(internal_secret=secret)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/v1/internal/notifications/scan", headers={"X-Internal-Secret": secret}
        )
    finally:
        internal_auth_module.get_settings = original_get_settings

    assert response.status_code == 200
    assert response.json() == {"scanned": 1, "notified": 0, "skipped": 1}
    assert spy.calls == []  # never even attempted -- on cadence, nothing to nudge
