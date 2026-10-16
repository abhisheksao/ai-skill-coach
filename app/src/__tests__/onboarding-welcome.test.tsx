/** 005 US5, research.md R12: the first-run explainer's gating rules --
 * shown exactly once, between the profile step and the dashboard;
 * skippable; never re-shown after completion. `resolveOnboardingRedirect`
 * is the auth gate's routing decision extracted as a pure function
 * (_layout.tsx calls it directly) specifically so this doesn't require
 * mounting the full navigator/auth-context tree. Also covers the
 * contextual-permission half of R12: notification permission is only
 * ever requested by the explainer's own exported action, never silently. */
import * as Notifications from 'expo-notifications';

import { requestPushPermissionAndRegister } from '@/hooks/use-push-notifications';
import { postPushToken } from '@/lib/api';
import { isWelcomeSeen, markWelcomeSeen, resolveOnboardingRedirect } from '@/lib/onboarding';

// AsyncStorage's native module isn't available under plain jest-expo --
// same official-mock pattern as dashboard-cache.test.ts.
jest.mock('@react-native-async-storage/async-storage', () =>
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  setNotificationHandler: jest.fn(),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  useLastNotificationResponse: jest.fn(),
}));

jest.mock('@/lib/api', () => ({
  postPushToken: jest.fn(),
  deletePushToken: jest.fn(),
}));

const mockedNotifications = Notifications as jest.Mocked<typeof Notifications>;
const mockedPostPushToken = postPushToken as jest.Mock;

describe('requestPushPermissionAndRegister (005 R12: the ONE contextual prompt)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('escalates to the real OS prompt when status is undetermined -- this is the explainer action, prompting IS expected here', async () => {
    mockedNotifications.getPermissionsAsync.mockResolvedValue({ granted: false } as never);
    mockedNotifications.requestPermissionsAsync.mockResolvedValue({ granted: true } as never);
    mockedNotifications.getExpoPushTokenAsync.mockResolvedValue({ data: 'tok-1' } as never);

    const result = await requestPushPermissionAndRegister();

    expect(mockedNotifications.requestPermissionsAsync).toHaveBeenCalledTimes(1);
    expect(mockedPostPushToken).toHaveBeenCalledWith('tok-1', expect.any(String));
    expect(result).toBe(true);
  });

  it('does not re-prompt when already granted, and still registers', async () => {
    mockedNotifications.getPermissionsAsync.mockResolvedValue({ granted: true } as never);
    mockedNotifications.getExpoPushTokenAsync.mockResolvedValue({ data: 'tok-1' } as never);

    await requestPushPermissionAndRegister();

    expect(mockedNotifications.requestPermissionsAsync).not.toHaveBeenCalled();
  });

  it('returns false and never registers a token when the user declines', async () => {
    mockedNotifications.getPermissionsAsync.mockResolvedValue({ granted: false } as never);
    mockedNotifications.requestPermissionsAsync.mockResolvedValue({ granted: false } as never);

    const result = await requestPushPermissionAndRegister();

    expect(result).toBe(false);
    expect(mockedPostPushToken).not.toHaveBeenCalled();
  });
});

describe('resolveOnboardingRedirect', () => {
  it('routes signed-out users to sign-in, from anywhere', () => {
    expect(
      resolveOnboardingRedirect({
        session: false,
        profile: false,
        welcomeSeen: false,
        segments: ['(main)', 'dashboard'],
      })
    ).toBe('/sign-in');
  });

  it('routes a signed-in user without a profile to the profile step', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: false,
        welcomeSeen: false,
        segments: ['(main)', 'dashboard'],
      })
    ).toBe('/profile');
  });

  it('shows welcome exactly once: profile done, not yet seen -> /welcome', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: false,
        segments: ['(main)', 'dashboard'],
      })
    ).toBe('/welcome');
  });

  it('regression: finishing the profile step (still on /profile, same (onboarding) group as /welcome) advances to /welcome instead of staying stuck -- an earlier version conflated the two screens via the group alone', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: false,
        segments: ['(onboarding)', 'profile'],
      })
    ).toBe('/welcome');
  });

  it('never re-shown after completion: profile done AND welcome seen -> no redirect from main', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: true,
        segments: ['(main)', 'dashboard'],
      })
    ).toBeNull();
  });

  it('skippable: welcome seen (via skip or completion) sends a stale auth/onboarding visit to the dashboard', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: true,
        segments: ['(auth)', 'sign-in'],
      })
    ).toBe('/dashboard');
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: true,
        segments: ['(onboarding)', 'welcome'],
      })
    ).toBe('/dashboard');
  });

  it('does not redirect away while already on the welcome/profile screen itself', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: false,
        welcomeSeen: false,
        segments: ['(onboarding)', 'profile'],
      })
    ).toBeNull();
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: false,
        segments: ['(onboarding)', 'welcome'],
      })
    ).toBeNull();
  });

  it('never redirects anywhere while the welcome-seen flag is still loading (null)', () => {
    expect(
      resolveOnboardingRedirect({
        session: true,
        profile: true,
        welcomeSeen: null,
        segments: ['(main)', 'dashboard'],
      })
    ).toBeNull();
    expect(
      resolveOnboardingRedirect({
        session: false,
        profile: false,
        welcomeSeen: null,
        segments: ['(main)', 'dashboard'],
      })
    ).toBeNull();
  });
});

describe('isWelcomeSeen / markWelcomeSeen', () => {
  it('defaults to not-seen before anything is written', async () => {
    expect(await isWelcomeSeen()).toBe(false);
  });

  it('is seen after markWelcomeSeen -- the persisted half of "never shown again"', async () => {
    await markWelcomeSeen();
    expect(await isWelcomeSeen()).toBe(true);
  });
});
