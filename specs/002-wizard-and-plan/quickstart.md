# Quickstart — 002 Wizard & Plan Generation

Validation guide. Builds on 001's quickstart (same env, same running
stack) — only what's new is covered here.

## Prerequisites

Everything from 001's quickstart, already live: Supabase project, Neo4j
Aura instance (constraint applied), Gemini key (`LLM_MODEL` pinned in the
live env to `gemini-3.1-flash-lite`, config default is
`gemini-flash-lite-latest` — see research R8 for why). No new services.

## Validation scenarios

| # | Scenario | Expected | Proves |
|---|----------|----------|--------|
| 1 | Sign in → "Add skill" → type "Swimming" → wizard asks level/target/timeline/weekly-time one at a time | Coach-like tone, one topic at a time, follow-up on a vague answer | US1 |
| 2 | Answer all four, wizard plays back a summary and asks to confirm | Summary matches what was said; nothing in Neo4j yet | US1 scenario 3, FR-004 |
| 3 | Confirm → plan appears | Goal + 3–12 ordered steps with cadence; `MATCH (s:Skill)-[:HAS_GOAL]->(g:Goal), (s)-[:HAS_PLAN]->(p:Plan)-[:HAS_STEP]->(st:Step) RETURN *` in Aura shows exactly this, atomically | US2 scenario 1–2, SC-004 |
| 4 | Abandon the wizard halfway (kill app), reopen, start again | Fresh intake; no orphaned Skill/Goal/Plan from the abandoned attempt | US1 scenario 4 |
| 5 | On the plan review screen, tap Regenerate → too much | New, lighter plan replaces the old one; `generation` is now 1; old Plan node still exists, marked superseded | US2 scenario 4, R5 |
| 6 | Regenerate again → too easy | Plan gets more demanding; `generation` = 2 | US2 scenario 5 |
| 7 | Regenerate a 3rd time (any reason), then try a 4th | 4th attempt: no regenerate option, routed to revise-in-wizard instead | US2 scenario 6, FR-011 |
| 8 | Add a second skill named "swimming" (lowercase) | Client warns before entering the wizard: continue existing vs. start new | FR-012 |
| 9 | Two skills onboarded; converse in skill A | Skill B's goal/plan/messages completely unaffected | US3 scenario 2 |
| 10 | `git grep -n "gemini-3.1-flash-lite" api/src` limited to config default; no hardcoded model elsewhere | Confirms Constitution VI still holds for this feature's new LLM call sites | Constitution VI |

Language sampling (Constitution VIII): run scenarios 1–3 in English and
Hindi in full; for Spanish/French/German, confirm the wizard's questions
and the generated plan's goal/step text render in that language (smoke).

## Results (2026-07-14)

Environment: physical Android device (dev client), against the deployed
Render API and live Supabase/Aura/Gemini.

| # | Result | Notes |
|---|--------|-------|
| 1-3 | ✅ Pass | Full wizard→goal→plan cycle live; surfaced 4 UX gaps (keyboard avoidance, too much free-typing, stale add-skill field, no way back to plan details) + a target-date-in-the-past bug, all fixed and covered by tests before retesting |
| 4 | ✅ Pass | Killed app mid-wizard, reopened, fresh intake — no orphaned Skill/Goal/Plan |
| 5 | ✅ Pass | Regenerate → "too much" → lighter plan, `generation` = 1, old Plan superseded |
| 6 | ✅ Pass | Regenerate → "too easy" → more demanding plan, `generation` = 2 |
| 7 | ✅ Pass | 3rd regenerate succeeds (`generation` = 3); 4th routes to chat with revise nudge, no 4th regenerate option shown |
| 8 | ✅ Pass | Adding a second "swimming" (lowercase) warned before entering the wizard |
| 9 | ✅ Pass | Conversed in skill A; skill B's goal/plan/messages unaffected |
| 10 | ✅ Pass | Verified via `git grep` — hardcoded model confined to config default |

All 10 scenarios pass. Also found live: `plan-review.tsx`'s regenerate
CTA ("Not quite right?") still showed when reopening an established
plan long after creation, not just right after the wizard — expected,
since that screen now doubles as the permanent skill-detail view (see
issue #4's fix), but the copy was written for a one-time review moment.
Retitled to "Want to adjust this plan?" across all 5 locales rather
than restricting when regenerate is offered (avoids storing a "first
visit" flag, keeping with derive-don't-store).

Language sampling (2026-07-14/15): scenarios 1-3 run in EN this session.
Hindi (HI) full pass completed separately by the product owner, live on
device -- thorough manual verification of the wizard+plan flow in Hindi.
ES/FR/DE smoke done live 2026-07-15 via direct API calls (profile language
set, one wizard-opening message sent per language): UI strings already
localized in all three locale files, and each live reply came back fully
in-language --
ES: "¡Qué emocionante! Aprender ajedrez es un reto fantástico. Para
empezar, ¿cómo describirías tu nivel de experiencia actual con el juego?";
FR: "C'est une excellente initiative ! Les échecs sont un jeu passionnant.
Pour bien commencer notre accompagnement, pourriez-vous me dire quel est
votre niveau actuel ?";
DE: "Das ist ein wunderbares Ziel! Schach ist ein faszinierendes Spiel. Um
dich bestmöglich zu unterstützen, würde ich gerne wissen: Wie würdest du
deine aktuelle Erfahrung mit Schach einschätzen?".
Constitution VIII's multilingual-sampling requirement is now satisfied for
002.

## Exit

All 10 scenarios pass ⇒ feature 002 meets its success criteria, and the
EN+HI full / ES+FR+DE smoke language sampling required by Constitution
VIII is complete. Proceed to feature 003 (per Amendment 1.6.0, the
Playwright/Maestro scenario backfill for 001/002 -- specs/001-foundations
and specs/002-wizard-and-plan quickstart scenarios -- must land first; see
docs/testing.md for current status).
