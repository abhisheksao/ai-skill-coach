/** First-run explainer gating (005, US5, research.md R12) -- shown once
 * after the post-signup profile step completes, never again after that.
 * Same AsyncStorage-flag pattern as dashboard-cache.ts's offline cache. */
import AsyncStorage from '@react-native-async-storage/async-storage';

const WELCOME_SEEN_KEY = 'skillcoach.onboarding-welcome-seen.v1';

export async function isWelcomeSeen(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(WELCOME_SEEN_KEY)) === 'true';
  } catch {
    return false;
  }
}

export async function markWelcomeSeen(): Promise<void> {
  try {
    await AsyncStorage.setItem(WELCOME_SEEN_KEY, 'true');
  } catch {
    // Best-effort -- worst case the explainer shows again next launch.
  }
}

export type OnboardingRedirect = '/sign-in' | '/profile' | '/welcome' | '/dashboard' | null;

/** The auth gate's routing decision as a pure function (_layout.tsx calls
 * this directly) -- extracted so the "show welcome exactly once, between
 * profile and dashboard" rule is unit-testable without mounting the full
 * navigator/auth-context tree. `null` means "stay on the current route".
 * `welcomeSeen: null` (still loading from AsyncStorage) always yields
 * `null` -- the gate must not redirect anywhere until it knows.
 *
 * Takes the full segment path, not just the top-level group: `/profile`
 * and `/welcome` both live under the `(onboarding)` group, so checking
 * only `segments[0]` can't tell "still on /profile, must advance to
 * /welcome" apart from "already on /welcome, stay put" -- an earlier
 * version of this function collapsed both cases to "in the onboarding
 * group, never redirect", which permanently stranded a user on /profile
 * after completing it (found via live e2e replay, not the unit tests --
 * that version's own test suite had encoded the bug as expected
 * behavior). */
export function resolveOnboardingRedirect(input: {
  session: boolean;
  profile: boolean;
  welcomeSeen: boolean | null;
  segments: readonly string[];
}): OnboardingRedirect {
  const { session, profile, welcomeSeen, segments } = input;
  const group = segments[0];
  const screen = segments[1];
  if (welcomeSeen === null) return null;

  if (!session) return group !== '(auth)' ? '/sign-in' : null;
  if (!profile) return screen !== 'profile' ? '/profile' : null;
  if (!welcomeSeen) return screen !== 'welcome' ? '/welcome' : null;
  if (group === '(auth)' || group === '(onboarding)') return '/dashboard';
  return null;
}
