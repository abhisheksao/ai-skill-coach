"""GET /v1/skills, GET /v1/skills/{id} (list pulled forward from Phase 3
into Phase 2 for the app-side duplicate-name check, FR-012), and
POST /v1/skills/{id}/plan/regenerate (T016).
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from tests.fakes import (
    FakeBudget,
    FakeCadenceSchedule,
    FakeIntentApply,
    FakeJwksClient,
    FakeMessages,
)

pytestmark = [pytest.mark.wizard_plan, pytest.mark.skills, pytest.mark.regenerate]


class FakeSkills:
    def __init__(
        self, skills: list[dict], detail: dict | None = None, detail_after: dict | None = None
    ) -> None:
        self._skills = skills
        self._detail = detail
        self._detail_after = detail_after or detail
        self.calls: list[str] = []
        self.detail_calls: list[tuple[str, str]] = []

    async def list_skills(self, user_id: str):
        from skillcoach_api.models.skills import SkillSummary

        self.calls.append(user_id)
        return [SkillSummary(**s) for s in self._skills]

    async def get_skill(self, user_id: str, skill_id: str):
        from skillcoach_api.models.skills import SkillDetail

        self.detail_calls.append((user_id, skill_id))
        # First call = pre-regenerate read; subsequent calls = post-apply
        # re-read, so tests can prove the response reflects fresh state.
        source = self._detail if len(self.detail_calls) <= 1 else self._detail_after
        return SkillDetail(**source) if source else None


@pytest.fixture
def skills_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    return create_app()


def test_list_skills_returns_caller_scoped_cards(skills_app, make_token) -> None:
    fake = FakeSkills(
        [
            {
                "id": "skill-1",
                "name": "Swimming",
                "created_at": "2026-07-14T09:00:00Z",
                "goal_statement": "Swim 1km",
                "target_date": "2026-12-01",
                "step_count": 3,
            }
        ]
    )
    skills_app.state.services = SimpleNamespace(skills=fake)
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/skills", headers={"Authorization": f"Bearer {make_token(sub='user-1')}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["skills"]) == 1
    assert body["skills"][0]["name"] == "Swimming"
    assert fake.calls == ["user-1"]  # scoped to the authenticated sub


def test_list_skills_requires_auth(skills_app) -> None:
    skills_app.state.services = SimpleNamespace(skills=FakeSkills([]))
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = client.get("/v1/skills")
    assert response.status_code == 401


def test_get_skill_returns_detail(skills_app, make_token) -> None:
    fake = FakeSkills(
        [],
        detail={
            "id": "skill-1",
            "name": "Swimming",
            "goal": {"statement": "Swim 1km", "target_date": "2026-12-01"},
            "plan": {
                "id": "plan-1",
                "generation": 0,
                "steps": [{"order": 1, "description": "Float", "cadence_per_week": 3}],
            },
        },
    )
    skills_app.state.services = SimpleNamespace(skills=fake)
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/skills/skill-1", headers={"Authorization": f"Bearer {make_token(sub='user-1')}"}
    )

    assert response.status_code == 200
    assert response.json()["plan"]["generation"] == 0
    assert fake.detail_calls == [("user-1", "skill-1")]


def test_get_skill_404_when_missing_or_not_owned(skills_app, make_token) -> None:
    skills_app.state.services = SimpleNamespace(skills=FakeSkills([], detail=None))
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = client.get("/v1/skills/nope", headers={"Authorization": f"Bearer {make_token()}"})
    assert response.status_code == 404


# ------------------------------------------------------------------------
# POST /v1/skills/{id}/plan/regenerate (T016)
# ------------------------------------------------------------------------


class FakeLlmForRegenerate:
    def __init__(self, turns: list) -> None:
        self._turns = iter(turns)
        self.calls: list[tuple] = []

    async def generate_regeneration(self, context, reason, note, force_different=False):
        self.calls.append((reason, note, force_different))
        return next(self._turns), None


BASE_DETAIL = {
    "id": "skill-1",
    "name": "Swimming",
    "goal": {"statement": "Swim 1km", "target_date": "2026-12-01"},
    "plan": {
        "id": "plan-0",
        "generation": 0,
        "steps": [
            {"order": 1, "description": "Float and glide", "cadence_per_week": 3},
            {"order": 2, "description": "Kick drills", "cadence_per_week": 3},
            {"order": 3, "description": "Full stroke", "cadence_per_week": 2},
        ],
    },
}


def _revise_plan_turn(reply: str, steps: list[dict]):
    from skillcoach_api.models.chat import ChatTurn
    from skillcoach_api.models.intents import RevisePlanIntent, StepPayload

    return ChatTurn(
        reply=reply,
        intents=[
            RevisePlanIntent(
                type="revise_plan",
                skill_name="Swimming",
                steps=[StepPayload(**s) for s in steps],
            )
        ],
    )


def _wire_regenerate(skills_app, *, detail, detail_after=None, llm_turns):
    fake_skills = FakeSkills([], detail=detail, detail_after=detail_after)
    fake_llm = FakeLlmForRegenerate(llm_turns)
    fake_intent_apply = FakeIntentApply()
    services = SimpleNamespace(
        skills=fake_skills,
        llm=fake_llm,
        intent_apply=fake_intent_apply,
        budget=FakeBudget(),
        messages=FakeMessages(language="en"),
        cadence_schedule=FakeCadenceSchedule(),
    )
    skills_app.state.services = services
    return services, fake_skills, fake_llm, fake_intent_apply


def _post_regenerate(client, token, skill_id="skill-1", reason="too_much", note=None):
    body = {"reason": reason}
    if note is not None:
        body["note"] = note
    return client.post(
        f"/v1/skills/{skill_id}/plan/regenerate",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_regenerate_happy_path_applies_once(skills_app, make_token) -> None:
    different_steps = [
        {"order": 1, "description": "Breathing at the wall", "cadence_per_week": 2},
        {"order": 2, "description": "Treading water", "cadence_per_week": 2},
        {"order": 3, "description": "Backstroke intro", "cadence_per_week": 1},
    ]
    after = {**BASE_DETAIL, "plan": {"id": "plan-1", "generation": 1, "steps": different_steps}}
    services, fake_skills, fake_llm, fake_apply = _wire_regenerate(
        skills_app,
        detail=BASE_DETAIL,
        detail_after=after,
        llm_turns=[_revise_plan_turn("Here's a gentler plan!", different_steps)],
    )
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = _post_regenerate(client, make_token(sub="user-1"), note="too intense")

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Here's a gentler plan!"
    assert body["plan"]["generation"] == 1
    assert len(fake_llm.calls) == 1  # no similarity retry needed
    assert fake_llm.calls[0] == ("too_much", "too intense", False)
    assert len(fake_apply.applied) == 1
    # 004: cadence_schedules synced with the newly APPLIED steps.
    assert len(services.cadence_schedule.synced) == 1
    _, _, synced_steps = services.cadence_schedule.synced[0]
    assert [s.description for s in synced_steps] == [s["description"] for s in different_steps]


def test_regenerate_at_cap_returns_409_with_no_llm_call(skills_app, make_token) -> None:
    at_cap = {**BASE_DETAIL, "plan": {**BASE_DETAIL["plan"], "generation": 3}}
    _, _, fake_llm, fake_apply = _wire_regenerate(skills_app, detail=at_cap, llm_turns=[])

    response = _post_regenerate(
        client=TestClient(skills_app, raise_server_exceptions=False), token=make_token()
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "regeneration_cap_reached"
    assert fake_llm.calls == []
    assert fake_apply.applied == []


def test_regenerate_similarity_guard_triggers_one_uncounted_retry(skills_app, make_token) -> None:
    # Route-level orchestration test (does it retry and use the SECOND
    # result?) -- exact duplicate steps guarantee "similar", so this isn't
    # re-testing the threshold itself (that's test_plan_similarity.py's job).
    near_identical_steps = list(BASE_DETAIL["plan"]["steps"])
    genuinely_different_steps = [
        {"order": 1, "description": "Breathing at the wall", "cadence_per_week": 2},
        {"order": 2, "description": "Treading water", "cadence_per_week": 2},
        {"order": 3, "description": "Backstroke intro", "cadence_per_week": 1},
    ]
    after = {
        **BASE_DETAIL,
        "plan": {"id": "plan-1", "generation": 1, "steps": genuinely_different_steps},
    }
    services, _, fake_llm, fake_apply = _wire_regenerate(
        skills_app,
        detail=BASE_DETAIL,
        detail_after=after,
        llm_turns=[
            _revise_plan_turn("Still working on it...", near_identical_steps),
            _revise_plan_turn("Okay, truly different this time!", genuinely_different_steps),
        ],
    )
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = _post_regenerate(client, make_token(sub="user-1"))

    assert response.status_code == 200
    assert response.json()["reply"] == "Okay, truly different this time!"
    # Two LLM calls (first + forced-different retry), but only ONE apply --
    # the near-duplicate result is discarded, never persisted.
    assert len(fake_llm.calls) == 2
    assert fake_llm.calls[0][2] is False  # force_different
    assert fake_llm.calls[1][2] is True
    # Regression: cadence_schedules must sync with the FINAL (genuinely
    # different) steps, never the discarded near-duplicate first attempt.
    assert len(services.cadence_schedule.synced) == 1
    _, _, synced_steps = services.cadence_schedule.synced[0]
    assert [s.description for s in synced_steps] == [
        s["description"] for s in genuinely_different_steps
    ]
    assert len(fake_apply.applied) == 1
    # generation moved by exactly one, proving the internal retry is
    # architecturally free -- one regeneration attempt, one Plan created.
    assert response.json()["plan"]["generation"] == 1


def test_regenerate_reason_and_note_reach_the_llm(skills_app, make_token) -> None:
    _, _, fake_llm, _ = _wire_regenerate(
        skills_app,
        detail=BASE_DETAIL,
        llm_turns=[_revise_plan_turn("ok", BASE_DETAIL["plan"]["steps"])],
    )
    client = TestClient(skills_app, raise_server_exceptions=False)

    _post_regenerate(client, make_token(), reason="not_quite_right", note="wrong focus entirely")

    assert fake_llm.calls[0] == ("not_quite_right", "wrong focus entirely", False)


def test_regenerate_404_when_skill_missing(skills_app, make_token) -> None:
    _, _, fake_llm, _ = _wire_regenerate(skills_app, detail=None, llm_turns=[])
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = _post_regenerate(client, make_token())

    assert response.status_code == 404
    assert fake_llm.calls == []


def test_regenerate_requires_auth(skills_app) -> None:
    _wire_regenerate(skills_app, detail=BASE_DETAIL, llm_turns=[])
    client = TestClient(skills_app, raise_server_exceptions=False)

    response = client.post("/v1/skills/skill-1/plan/regenerate", json={"reason": "too_much"})
    assert response.status_code == 401
