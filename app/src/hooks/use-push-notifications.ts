import type * as NotificationsModule from 'expo-notifications';
import { useRouter } from 'expo-router';
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

import { deletePushToken, postPushToken } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { extractSkillIdFromNotificationData, resolvePushPlatform } from '@/lib/push-notifications';

/** `expo-notifications` is excluded from iOS autolinking in package.json
 * (personal/free Apple Developer teams can't provision the aps-environment
 * capability this package's config plugin always adds -- see
 * ios/SkillCoach/SkillCoach.entitlements). With the native module gone, a
 * plain top-level `import * as Notifications from 'expo-notifications'`
 * throws synchronously ("Cannot find native module") during module
 * evaluation -- before any try/catch of ours runs -- which would crash the
 * app at launch on iOS. Loading it via a guarded `require` defers that
 * throw to here, where it's caught; every call site below fails soft
 * instead. `jest.mock('expo-notifications', ...)` (onboarding-welcome.test)
 * intercepts this same `require`, so the existing tests are unaffected.
 * Re-add the plain import once the paid Apple Developer Program is active
 * and the package.json exclude is reverted. */
let Notifications: typeof NotificationsModule | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Notifications = require('expo-notifications');
} catch {
  Notifications = null;
}

Notifications?.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

/** 005, research.md R12: permission prompts stay contextual -- this
 * silent path (called automatically on every sign-in below) never
 * escalates to the actual OS dialog when status is undetermined; it only
 * proceeds if permission was ALREADY granted in a prior session (e.g.
 * via the welcome explainer's "enable nudges" action, requestPush
 * PermissionAndRegister below). Previously this auto-requested on every
 * sign-in with no explanation shown first -- a real R12 violation found
 * while implementing the explainer, fixed here. */
async function registerForPushNotifications(): Promise<string | null> {
  if (!Notifications) return null;
  const existing = await Notifications.getPermissionsAsync();
  if (!existing.granted) return null;

  try {
    const { data: token } = await Notifications.getExpoPushTokenAsync();
    return token;
  } catch (error) {
    // Fails soft (matches GraphService.ensure_user's tolerance pattern) --
    // e.g. a device/emulator without real push capability, or a network
    // failure reaching Expo's push service. app.json's extra.eas.projectId
    // is set (docs/getting-started.md), so ERR_NOTIFICATIONS_NO_EXPERIENCE_ID
    // shouldn't recur; kept here as a safety net regardless. Every other
    // feature keeps working even when this fails.
    console.warn('Push token unavailable:', error);
    return null;
  }
}

/** The ONE place this app actually shows the native notification-
 * permission dialog (005, US5's onboarding explainer "enable nudges"
 * action) -- everywhere else only checks/uses an already-granted
 * permission. Registers the resulting token immediately so the pilot's
 * first nudge doesn't wait for the next app launch. */
export async function requestPushPermissionAndRegister(): Promise<boolean> {
  if (!Notifications) return false;
  const existing = await Notifications.getPermissionsAsync();
  const status = existing.granted ? existing : await Notifications.requestPermissionsAsync();
  if (!status.granted) return false;

  try {
    const { data: token } = await Notifications.getExpoPushTokenAsync();
    await postPushToken(token, resolvePushPlatform(Platform.OS));
    return true;
  } catch (error) {
    console.warn('Push token unavailable:', error);
    return false;
  }
}

/** Registers the Expo push token on sign-in, revokes it on sign-out, and
 * routes a notification tap to the deep-linked skill's session (FR-009,
 * FR-013). Deliberately does NOT also listen for native token-rotation
 * events (`addPushTokenListener`) -- that payload is the raw native
 * device token, not Expo-formatted, and calling `getExpoPushTokenAsync()`
 * from inside its own callback to re-derive a proper one creates an
 * infinite loop (that call itself emits another rotation event; found
 * live, 2026-07-18 -- see git history for the full incident). Rotation
 * mid-session is rare enough that "re-registers correctly on next app
 * launch" (this hook's other effect, keyed on `session`) is an acceptable
 * degradation, consistent with this file's existing fails-soft posture. */
function useNativePushNotifications(): void {
  // Only ever selected below when `Notifications` loaded successfully.
  const notifications = Notifications!;
  const { session } = useAuth();
  const router = useRouter();
  const registeredTokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!session) {
      const token = registeredTokenRef.current;
      if (token) {
        registeredTokenRef.current = null;
        deletePushToken(token).catch(() => {});
      }
      return;
    }

    let cancelled = false;
    registerForPushNotifications().then((token) => {
      if (cancelled || !token) return;
      registeredTokenRef.current = token;
      postPushToken(token, resolvePushPlatform(Platform.OS)).catch(() => {});
    });

    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    const subscription = notifications.addNotificationResponseReceivedListener((response) => {
      const skillId = extractSkillIdFromNotificationData(
        response.notification.request.content.data
      );
      if (skillId) {
        router.push({ pathname: '/chat', params: { skillId } });
      }
    });
    return () => subscription.remove();
  }, [router]);

  // Cold start: app was launched BY tapping a notification.
  const lastResponse = notifications.useLastNotificationResponse();
  useEffect(() => {
    if (!lastResponse) return;
    const skillId = extractSkillIdFromNotificationData(
      lastResponse.notification.request.content.data
    );
    if (skillId) {
      router.push({ pathname: '/chat', params: { skillId } });
    }
  }, [lastResponse, router]);
}

/** No-op on web. Found live, 2026-07-18: `Notifications.
 * useLastNotificationResponse()` doesn't just degrade gracefully on web
 * (unlike the rest of this module's calls) -- it throws a fatal, uncaught
 * error ("...getLastNotificationResponse is not available on web"),
 * called unconditionally from the ROOT layout, which crashed the entire
 * web build to a blank page on every single route, not just this one.
 * Push notifications are already out of scope for web in this app's
 * design; skip the native module entirely there rather than patch around
 * one throwing call when the rest of the surface isn't fully supported
 * either (a console warning already flags `addPushTokenListener` as a
 * no-op on web). `Platform.OS` is fixed for the app's lifetime, so
 * selecting the implementation at module scope -- rather than branching
 * inside a single hook body -- never violates React's rules of hooks. */
function useWebPushNotificationsNoop(): void {}

/** No-op when `expo-notifications` didn't load (see the guarded `require`
 * above -- excluded from iOS autolinking while on a personal Apple
 * Developer team). `Notifications` is resolved once at module scope and
 * never changes for the app's lifetime, so selecting the implementation
 * here -- rather than branching inside a single hook body -- never
 * violates React's rules of hooks, same reasoning as the web case below. */
function useUnavailablePushNotificationsNoop(): void {}

export const usePushNotifications: () => void = !Notifications
  ? useUnavailablePushNotificationsNoop
  : Platform.OS === 'web'
    ? useWebPushNotificationsNoop
    : useNativePushNotifications;
