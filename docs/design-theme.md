# Skill Coach — Design Theme (provisional)

Single source of design tokens for the app. **Status: provisional** — the palette
and logo are working choices made 2026-07-12 so implementation can proceed
consistently; the product owner may replace them later. Replacement must be a
token/asset swap only (constitution, Architectural Constraints), so implement
against the token names, never raw hex values.

## Brand idea

A coach that helps you climb, one small step at a time. The identity leans on two
motifs: **ascent** (rising steps, the growth curve) and **voice** (the coach speaks
and listens). Calm confidence over gamified loudness: teal→indigo does the everyday
work; amber appears only when something is worth celebrating.

## Color tokens

### Core palette

| Token | Light | Dark | Use |
|---|---|---|---|
| `color.primary` | `#0D9488` (teal 600) | `#2DD4BF` (teal 400) | Primary actions, active states, links, user chat bubble |
| `color.primary.pressed` | `#0F766E` | `#14B8A6` | Pressed/hover of primary |
| `color.secondary` | `#6366F1` (indigo 500) | `#818CF8` (indigo 400) | Secondary emphasis, plan/step accents, gradients with primary |
| `color.accent` | `#F59E0B` (amber 500) | `#FBBF24` (amber 400) | Celebration only: streaks, step-ups, milestones |
| `color.recording` | `#EF4444` (red 500) | `#F87171` | Push-to-talk active/recording state only |

### Surfaces & text

| Token | Light | Dark |
|---|---|---|
| `color.bg` | `#F8FAFC` (slate 50) | `#0F172A` (slate 900) |
| `color.surface` | `#FFFFFF` | `#1E293B` (slate 800) |
| `color.surface.raised` | `#FFFFFF` + shadow | `#334155` (slate 700) |
| `color.border` | `#E2E8F0` (slate 200) | `#334155` |
| `color.text` | `#0F172A` (slate 900) | `#F1F5F9` (slate 100) |
| `color.text.muted` | `#64748B` (slate 500) | `#94A3B8` (slate 400) |
| `color.text.on-primary` | `#FFFFFF` | `#042F2E` |

### Semantic

| Token | Light | Dark |
|---|---|---|
| `color.success` | `#16A34A` | `#4ADE80` |
| `color.warning` | `#D97706` | `#FBBF24` |
| `color.error` | `#DC2626` | `#F87171` |

### Gradient

`gradient.brand`: linear 135°, `#14B8A6` → `#6366F1`. Reserved for the logo,
onboarding hero, and empty states. Never behind body text.

## Usage rules

1. **Consistency beats novelty**: every screen uses these tokens; no per-screen
   colors. New needs → new token in this file first.
2. **Chat**: user bubbles `color.primary` with `text.on-primary`; coach bubbles
   `color.surface` with `color.text`. Identical in voice and chat modes.
3. **Push-to-talk**: idle = `color.primary`; recording = `color.recording` with a
   pulse; disabled/denied = `color.text.muted` outline + explanatory state.
4. **Amber is earned**: `color.accent` only for streaks, completed steps,
   difficulty step-ups, and celebration moments — never for ordinary UI chrome.
5. **Accessibility**: text/background pairs must meet WCAG AA (4.5:1 body,
   3:1 large text) in both modes. The pairs above pass; verify any new pair.
6. **Dark mode is first-class**: both modes ship from feature 001; tokens above
   define both.
7. **Multilingual layout** (Constitution X): strings vary widely in length
   (German long, Hindi tall glyphs) — components size to content, no fixed-width
   text boxes; Devanagari needs adequate line height (≥1.4).

## Typography

System font stack (SF Pro on iOS, Roboto on Android, system-ui on web) — free,
excellent multilingual coverage including Devanagari, zero load time.

| Token | Size/Weight | Use |
|---|---|---|
| `type.display` | 28 / bold | Screen titles, onboarding |
| `type.title` | 20 / semibold | Section heads, skill cards |
| `type.body` | 16 / regular | Chat, plan steps, default |
| `type.caption` | 13 / regular, `text.muted` | Timestamps, hints, cadence labels |

## Logo

`assets/branding/logo.svg` — circular badge, brand gradient field, white mark:
three rising steps with an ascending trajectory curve ending in a spark — ascent +
momentum; the circle itself reads as presence/voice. Provisional, replaceable.

- Scales to app icon (Expo `icon`/`adaptiveIcon`) and favicon; safe at 48 px.
- Keep clear space ≥ 10% of diameter around it; don't recolor the mark.
- Monochrome variant: white mark on `color.primary` disc (derive when needed).
