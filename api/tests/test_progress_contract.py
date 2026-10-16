"""GET /v1/skills/{id}/progress (User Story 2, FR-004) — shape/values
match ProgressService output for a fixture, two calls in a row agree (no
drift), and a missing/not-owned skill 404s like every other skill route.
GET /v1/dashboard (User Story 6, FR-014) — shape, per-skill staleness
flag, agreement with the per-skill endpoint (SC-006), and the zero-skills
empty response."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api import constants
from skillcoach_api.main import create_app
from skillcoach_api.services.progress import SkillProgress, StepProgress
from tests.fakes import FakeJwksClient

pytestmark = [pytest.mark.progress_notifications, pytest.mark.dashboard]


class FakeSkills:
    def __init__(self, detail=None, summaries=None) -> None:
        self.detail = detail  # SkillDetail-shaped | dict[skill_id, that] | None
        self.summaries = summaries or []

    async def get_skill(self, _user_id: str, skill_id: str):
        if isinstance(self.detail, dict):
            return self.detail.get(skill_id)
        return self.detail

    async def list_skills(self, _user_id: str):
        return self.summaries


class FakeMessages:
    async def profile_timezone(self, _user_id: str) -> str:
        return "UTC"


class FakeProgress:
    def __init__(self, progress: SkillProgress | dict[str, SkillProgress]) -> None:
        self._progress = progress
        self.calls: list[tuple] = []

    async def compute(self, user_id: str, skill_id: str, timezone: str) -> SkillProgress:
        self.calls.append((user_id, skill_id, timezone))
        if isinstance(self._progress, dict):
            return self._progress[skill_id]
        return self._progress


FIXTURE_PROGRESS = SkillProgress(
    skill_id="skill-1",
    completed_steps=[1],
    total_steps=2,
    streak_days=4,
    steps=[
        StepProgress(
            order=1,
            completed=True,
            behind_cadence=False,
            last_checkin_at=datetime(2026, 7, 19, 18, 0, tzinfo=UTC),
            anchor_at=datetime(2026, 7, 19, 18, 0, tzinfo=UTC),
        ),
        StepProgress(
            order=2,
            completed=False,
            behind_cadence=True,
            last_checkin_at=None,
            anchor_at=datetime.now(UTC) - timedelta(days=30),
        ),
    ],
)


@pytest.fixture
def progress_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    return create_app()


def test_progress_shape_and_values_match_the_service_output(progress_app, make_token) -> None:
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(detail=SimpleNamespace(id="skill-1")),
        messages=FakeMessages(),
        progress=FakeProgress(FIXTURE_PROGRESS),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/skills/skill-1/progress",
        headers={"Authorization": f"Bearer {make_token(sub='user-1')}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "skill-1"
    assert body["completed_steps"] == [1]
    assert body["total_steps"] == 2
    assert body["streak_days"] == 4
    assert body["steps"][0] == {
        "order": 1,
        "completed": True,
        "behind_cadence": False,
        "last_checkin_at": "2026-07-19T18:00:00Z",
    }
    assert body["steps"][1]["completed"] is False
    assert body["steps"][1]["behind_cadence"] is True
    assert body["steps"][1]["last_checkin_at"] is None
    # anchor_at (internal-only) never leaks into the public shape.
    assert "anchor_at" not in body["steps"][1]


def test_two_requests_in_a_row_return_identical_values(progress_app, make_token) -> None:
    """FR-004/Constitution II: no stored counter to drift -- recomputing
    from the same underlying data must be byte-identical."""
    fake_progress = FakeProgress(FIXTURE_PROGRESS)
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(detail=SimpleNamespace(id="skill-1")),
        messages=FakeMessages(),
        progress=fake_progress,
    )
    client = TestClient(progress_app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {make_token(sub='user-1')}"}

    first = client.get("/v1/skills/skill-1/progress", headers=headers)
    second = client.get("/v1/skills/skill-1/progress", headers=headers)

    assert first.json() == second.json()
    assert len(fake_progress.calls) == 2  # genuinely recomputed each time, not cached


def test_progress_scoped_to_the_authenticated_user(progress_app, make_token) -> None:
    fake_progress = FakeProgress(FIXTURE_PROGRESS)
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(detail=SimpleNamespace(id="skill-1")),
        messages=FakeMessages(),
        progress=fake_progress,
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    client.get(
        "/v1/skills/skill-1/progress",
        headers={"Authorization": f"Bearer {make_token(sub='user-42')}"},
    )

    assert fake_progress.calls == [("user-42", "skill-1", "UTC")]


def test_progress_404s_for_a_missing_or_not_owned_skill(progress_app, make_token) -> None:
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(detail=None),
        messages=FakeMessages(),
        progress=FakeProgress(FIXTURE_PROGRESS),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/skills/missing-skill/progress",
        headers={"Authorization": f"Bearer {make_token(sub='user-1')}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_progress_requires_auth(progress_app) -> None:
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(detail=SimpleNamespace(id="skill-1")),
        messages=FakeMessages(),
        progress=FakeProgress(FIXTURE_PROGRESS),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get("/v1/skills/skill-1/progress")
    assert response.status_code == 401


# --------------------------------------------------------------- dashboard


def make_summary(skill_id: str, created_at: datetime, name: str = "Swimming") -> SimpleNamespace:
    return SimpleNamespace(
        id=skill_id,
        name=name,
        created_at=created_at,
        goal_statement="Swim 1km",
        target_date=date(2026, 12, 1),
        step_count=2,
    )


def make_detail(
    skill_id: str, step_orders_and_descriptions: list[tuple[int, str]]
) -> SimpleNamespace:
    return SimpleNamespace(
        id=skill_id,
        plan=SimpleNamespace(
            steps=[
                SimpleNamespace(order=order, description=description)
                for order, description in step_orders_and_descriptions
            ]
        ),
    )


def test_dashboard_shape_and_per_skill_staleness_flag(progress_app, make_token) -> None:
    now = datetime.now(UTC)
    on_cadence = SkillProgress(
        skill_id="skill-1",
        completed_steps=[1],
        total_steps=2,
        streak_days=4,
        steps=[
            StepProgress(
                order=1,
                completed=True,
                behind_cadence=False,
                last_checkin_at=now - timedelta(days=1),
                anchor_at=now - timedelta(days=1),
            )
        ],
    )
    stale = SkillProgress(
        skill_id="skill-2",
        completed_steps=[],
        total_steps=1,
        streak_days=0,
        steps=[
            StepProgress(
                order=1,
                completed=False,
                behind_cadence=True,
                last_checkin_at=None,
                anchor_at=now - timedelta(days=constants.STALE_GOAL_DAYS + 5),
            )
        ],
    )
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(
            detail={
                "skill-1": make_detail("skill-1", [(1, "Float and glide")]),
                "skill-2": make_detail("skill-2", [(1, "Kick drills")]),
            },
            summaries=[
                make_summary("skill-1", now - timedelta(days=60)),
                make_summary("skill-2", now - timedelta(days=constants.STALE_GOAL_DAYS + 5)),
            ],
        ),
        messages=FakeMessages(),
        progress=FakeProgress({"skill-1": on_cadence, "skill-2": stale}),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/dashboard", headers={"Authorization": f"Bearer {make_token(sub='user-1')}"}
    )

    assert response.status_code == 200
    body = response.json()
    cards = {c["skill_id"]: c for c in body["skills"]}
    assert cards["skill-1"]["is_stale"] is False
    assert cards["skill-1"]["progress"] == {
        "completed_steps": 1,
        "total_steps": 2,
        "streak_days": 4,
    }
    assert cards["skill-1"]["steps"] == [
        {"order": 1, "description": "Float and glide", "completed": True, "behind_cadence": False}
    ]
    assert cards["skill-2"]["is_stale"] is True
    assert cards["skill-2"]["progress"]["completed_steps"] == 0
    assert cards["skill-2"]["steps"][0]["behind_cadence"] is True


def test_dashboard_agrees_with_the_per_skill_progress_endpoint(progress_app, make_token) -> None:
    """SC-006: both endpoints derive from the same ProgressService.compute
    call -- the dashboard card's counts must equal the per-skill
    endpoint's, just summarized to a count instead of a step list."""
    detail = make_detail("skill-1", [(1, "Float and glide"), (2, "Kick drills")])
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(
            detail=detail,
            summaries=[make_summary("skill-1", datetime.now(UTC) - timedelta(days=5))],
        ),
        messages=FakeMessages(),
        progress=FakeProgress(FIXTURE_PROGRESS),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {make_token(sub='user-1')}"}

    dashboard = client.get("/v1/dashboard", headers=headers).json()
    per_skill = client.get("/v1/skills/skill-1/progress", headers=headers).json()

    card = dashboard["skills"][0]
    assert card["progress"]["completed_steps"] == len(per_skill["completed_steps"])
    assert card["progress"]["total_steps"] == per_skill["total_steps"]
    assert card["progress"]["streak_days"] == per_skill["streak_days"]


def test_dashboard_returns_empty_list_for_zero_skills(progress_app, make_token) -> None:
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(summaries=[]),
        messages=FakeMessages(),
        progress=FakeProgress(FIXTURE_PROGRESS),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/dashboard", headers={"Authorization": f"Bearer {make_token(sub='user-1')}"}
    )

    assert response.status_code == 200
    assert response.json() == {"skills": []}


def test_dashboard_staleness_boundary_is_inclusive_of_the_exact_threshold(
    progress_app, make_token
) -> None:
    """Boundary at exactly STALE_GOAL_DAYS -- a skill created (or last
    active) exactly that long ago is NOT yet stale."""
    now = datetime.now(UTC)
    at_boundary = now - timedelta(days=constants.STALE_GOAL_DAYS) + timedelta(seconds=2)
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(
            detail=make_detail("skill-1", [(1, "Float and glide")]),
            summaries=[make_summary("skill-1", at_boundary)],
        ),
        messages=FakeMessages(),
        progress=FakeProgress(
            SkillProgress(
                skill_id="skill-1", completed_steps=[], total_steps=0, streak_days=0, steps=[]
            )
        ),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get(
        "/v1/dashboard", headers={"Authorization": f"Bearer {make_token(sub='user-1')}"}
    )

    assert response.json()["skills"][0]["is_stale"] is False


def test_dashboard_requires_auth(progress_app) -> None:
    progress_app.state.services = SimpleNamespace(
        skills=FakeSkills(summaries=[]),
        messages=FakeMessages(),
        progress=FakeProgress(FIXTURE_PROGRESS),
    )
    client = TestClient(progress_app, raise_server_exceptions=False)

    response = client.get("/v1/dashboard")
    assert response.status_code == 401
