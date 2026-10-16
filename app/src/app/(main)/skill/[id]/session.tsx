import { Redirect, useLocalSearchParams } from 'expo-router';

/** Deep-link target for `skillcoach://skill/{id}/session` (004, FR-009).
 * Immediately redirects into an ordinary coaching conversation for that
 * skill — the gap-aware opening comes entirely from ContextBuilder
 * already including cadence-gap data server-side (context_builder.py),
 * not from anything this route itself carries. Signed-out users are
 * already redirected to sign-in by the root auth gate (_layout.tsx)
 * regardless of which screen was requested, so that Edge Case needs no
 * extra handling here; an unresolvable/missing id falls back to the
 * dashboard rather than crashing. */
export default function SkillSession() {
  const { id } = useLocalSearchParams<{ id?: string }>();

  if (!id) {
    return <Redirect href="/dashboard" />;
  }
  return <Redirect href={{ pathname: '/chat', params: { skillId: id } }} />;
}
