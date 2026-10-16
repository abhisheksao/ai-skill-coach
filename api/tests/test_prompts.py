"""Prompt builders (T008), tested directly rather than only incidentally
through LlmService: turn-cap boundary, each regenerate reason's distinct
instruction, force_different directive, and the unknown-language-code
fallback (negative/unknown-input path)."""

from datetime import date

import pytest

from skillcoach_api.models.skills import GoalDetail, PlanDetail, SkillDetail, StepDetail
from skillcoach_api.services.context_builder import ConversationContext
from skillcoach_api.services.prompts import (
    MAX_WIZARD_TURNS,
    build_coaching_prompt,
    build_regenerate_prompt,
    build_wizard_prompt,
)

pytestmark = [pytest.mark.wizard_plan, pytest.mark.progress_notifications, pytest.mark.prompts]

SKILL = SkillDetail(
    id="skill-1",
    name="Swimming",
    goal=GoalDetail(statement="Swim 1km", target_date=date(2026, 12, 1)),
    plan=PlanDetail(
        id="plan-1",
        generation=0,
        steps=[StepDetail(order=1, description="Float and glide", cadence_per_week=3)],
    ),
)


def make_context(
    turn_count: int = 0,
    skill: SkillDetail | None = None,
    language: str = "en",
    gap_description: str | None = None,
    recent_session_summaries: list[str] | None = None,
    goal_history: list[GoalDetail] | None = None,
):
    return ConversationContext(
        language=language,
        skill=skill,
        recent_messages=[],
        user_turn_count=turn_count,
        gap_description=gap_description,
        recent_session_summaries=recent_session_summaries or [],
        goal_history=goal_history or [],
    )


def test_wizard_prompt_not_yet_forced_below_the_cap() -> None:
    prompt = build_wizard_prompt("Chess", make_context(turn_count=MAX_WIZARD_TURNS - 2))
    assert f"turn {MAX_WIZARD_TURNS - 1} of a maximum {MAX_WIZARD_TURNS}" in prompt
    assert "You MUST summarize" not in prompt


def test_wizard_prompt_forces_summary_at_the_cap() -> None:
    prompt = build_wizard_prompt("Chess", make_context(turn_count=MAX_WIZARD_TURNS - 1))
    assert f"turn {MAX_WIZARD_TURNS} of a maximum {MAX_WIZARD_TURNS}" in prompt
    assert "You MUST summarize" in prompt


def test_wizard_prompt_names_the_skill_and_states_todays_date() -> None:
    prompt = build_wizard_prompt("Chess", make_context())
    assert '"Chess"' in prompt
    assert date.today().isoformat() in prompt


def test_coaching_prompt_summarizes_current_goal_and_steps() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "Swimming" in prompt
    assert "Swim 1km" in prompt
    assert "Float and glide" in prompt


def test_coaching_prompt_opens_by_naming_the_gap_supportively_when_behind() -> None:
    prompt = build_coaching_prompt(
        make_context(skill=SKILL, gap_description="Float and glide — 5 day(s) since last check-in")
    )
    assert "Float and glide — 5 day(s) since last check-in" in prompt
    assert "supportively, never punitively" in prompt


def test_coaching_prompt_weaves_in_recent_session_summaries_when_present() -> None:
    prompt = build_coaching_prompt(
        make_context(
            skill=SKILL,
            recent_session_summaries=[
                "Struggled with flip turns, felt discouraged.",
                "Great progress on float drills.",
            ],
        )
    )
    assert "Struggled with flip turns, felt discouraged." in prompt
    assert "Great progress on float drills." in prompt
    assert "without just reciting the list" in prompt


def test_coaching_prompt_has_no_session_history_note_when_none_exist() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL, recent_session_summaries=[]))
    assert "Recent session history" not in prompt


def test_coaching_prompt_references_the_goal_trajectory_when_revised() -> None:
    history = [
        GoalDetail(statement="Swim 1km", target_date=date(2026, 10, 1)),
        GoalDetail(statement="Swim 2km", target_date=date(2026, 11, 1)),
        GoalDetail(statement="Swim 1km", target_date=date(2026, 12, 1)),  # current, == SKILL.goal
    ]
    prompt = build_coaching_prompt(make_context(skill=SKILL, goal_history=history))

    assert "revised before" in prompt
    assert '"Swim 1km" (target 2026-10-01)' in prompt
    assert '"Swim 2km" (target 2026-11-01)' in prompt
    # The CURRENT goal (last entry) isn't repeated in the "earlier version(s)" list.
    assert prompt.count('"Swim 1km"') == 1


def test_coaching_prompt_has_no_trajectory_note_with_a_single_goal() -> None:
    """Only the current goal, no revisions -- nothing to reference."""
    history = [GoalDetail(statement="Swim 1km", target_date=date(2026, 12, 1))]
    prompt = build_coaching_prompt(make_context(skill=SKILL, goal_history=history))

    assert "revised before" not in prompt


def test_coaching_prompt_has_no_trajectory_note_when_history_is_empty() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL, goal_history=[]))
    assert "revised before" not in prompt


def test_coaching_prompt_has_no_gap_note_when_nothing_is_behind() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL, gap_description=None))
    assert "behind on this" not in prompt


def test_regenerate_prompt_too_much_asks_to_reduce_intensity() -> None:
    prompt = build_regenerate_prompt(make_context(skill=SKILL), "too_much", None, False)
    assert "reduce intensity" in prompt
    assert "User note:" not in prompt


def test_regenerate_prompt_too_easy_asks_to_increase_intensity() -> None:
    prompt = build_regenerate_prompt(make_context(skill=SKILL), "too_easy", None, False)
    assert "increase intensity" in prompt


def test_regenerate_prompt_not_quite_right_includes_the_note() -> None:
    prompt = build_regenerate_prompt(
        make_context(skill=SKILL), "not_quite_right", "too much running", False
    )
    assert "address the user's note directly" in prompt
    assert 'User note: "too much running"' in prompt


def test_regenerate_prompt_force_different_adds_directive() -> None:
    prompt = build_regenerate_prompt(make_context(skill=SKILL), "too_much", None, True)
    assert "MEANINGFULLY DIFFERENT" in prompt


def test_regenerate_prompt_without_force_different_omits_directive() -> None:
    prompt = build_regenerate_prompt(make_context(skill=SKILL), "too_much", None, False)
    assert "MEANINGFULLY DIFFERENT" not in prompt


def test_coaching_prompt_documents_all_three_checkin_intents_grounded_in_plan_steps() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "complete_step (step_order, sentiment)" in prompt
    assert 'log_checkin (step_order, outcome="partial", sentiment' in prompt
    assert "report_obstacle (step_order, obstacle, sentiment)" in prompt
    # step_order is grounded in the plan already summarized in the prompt.
    assert "1. Float and glide (3x/week)" in prompt


def test_coaching_prompt_states_the_ambiguous_report_clarifying_rule() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "ask ONE clarifying question instead of guessing" in prompt


def test_coaching_prompt_warns_against_inferring_ambiguity_from_recency() -> None:
    """Found live, 2026-07-18: mid-conversation about a step's obstacle,
    "I practiced some stuff yesterday" (no step/activity named) got
    silently logged as a check-in against that step instead of a
    clarifying question -- the model treated "most recently discussed"
    as if it were "referenced". A first, purely descriptive fix for
    this (asserted by this test's earlier version) did NOT change the
    live model's behavior on retest -- replaced with a concrete
    worked few-shot example instead, since that's what actually steers
    output format/behavior reliably."""
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "VAGUE-REPORT RULE" in prompt
    assert "I practiced some stuff yesterday" in prompt
    assert "Correct move: emit NO intent" in prompt


def test_coaching_prompt_states_asking_and_emitting_an_intent_are_mutually_exclusive() -> None:
    """Second live retest, 2026-07-18: the VAGUE-REPORT few-shot example
    alone got the model to ask a clarifying question -- progress -- but
    it ALSO still emitted a check-in intent the same turn (for an
    earlier, actually-unambiguous obstacle report from a prior message),
    defeating the point. This mechanical, judgment-free rule closes that
    gap: a clarifying turn emits zero intents, full stop."""
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "MUTUAL-EXCLUSIVITY RULE" in prompt
    assert "a clarifying turn emits ZERO check-in intents" in prompt
    assert "I practiced some stuff yesterday" in prompt


def test_coaching_prompt_gives_distinct_guidance_per_outcome() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "genuine celebration" in prompt  # complete_step
    assert "acknowledge the specific effort" in prompt  # log_checkin
    assert "concrete workaround or adjustment" in prompt  # report_obstacle


def test_coaching_prompt_explains_backdated_timestamps() -> None:
    prompt = build_coaching_prompt(make_context(skill=SKILL))
    assert "over the weekend" in prompt
    assert "omit it to mean right now" in prompt


def test_unknown_language_code_falls_back_to_english() -> None:
    prompt = build_wizard_prompt("Chess", make_context(language="xx"))
    assert "Always reply in English." in prompt


def test_known_language_code_used_verbatim() -> None:
    prompt = build_wizard_prompt("Chess", make_context(language="hi"))
    assert "Always reply in Hindi." in prompt
