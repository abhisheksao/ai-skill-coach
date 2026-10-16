import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';

import '@/i18n';
import { usePushNotifications } from '@/hooks/use-push-notifications';
import { AuthProvider, useAuth } from '@/lib/auth-context';
import { isWelcomeSeen, resolveOnboardingRedirect } from '@/lib/onboarding';
import { useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

SplashScreen.preventAutoHideAsync();

/** Auth gate (T015, extended 005 US5): signed-out → sign-in; signed-in
 *  without profile → profile step (re-presented until completed, spec
 *  US3); profile done but the first-run explainer not yet seen →
 *  welcome (research.md R12); else → dashboard (004's home dashboard
 *  replaces 002's /skills landing). */
function RootNavigator() {
  const { session, profile, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const { colors } = useTheme();

  // Push-token registration/rotation/revocation + notification-tap
  // routing (004, FR-009/FR-013) — lives at the root so it's active
  // regardless of which screen is currently focused.
  usePushNotifications();

  useEffect(() => {
    if (loading) return;
    // Re-read the flag from AsyncStorage on every navigation-relevant
    // change instead of caching it in component state: welcome.tsx's
    // finish() writes the flag then does a plain `router.replace`, with
    // no equivalent of AuthContext's `refreshProfile()` to push the new
    // value back up here. A cached copy would still read stale
    // `welcomeSeen: false` right after that replace and immediately
    // redirect back to /welcome (confirmed live -- the explainer
    // reappeared, reset to its first card, right after "Enable nudges").
    let cancelled = false;
    isWelcomeSeen().then((welcomeSeen) => {
      if (cancelled) return;
      SplashScreen.hideAsync();
      const redirect = resolveOnboardingRedirect({
        session: !!session,
        profile: !!profile,
        welcomeSeen,
        segments,
      });
      if (redirect) router.replace(redirect);
    });
    return () => {
      cancelled = true;
    };
  }, [loading, session, profile, segments, router]);

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.bg },
      }}
    />
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <RootNavigator />
    </AuthProvider>
  );
}
