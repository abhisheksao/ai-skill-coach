import { Redirect } from 'expo-router';

export default function Index() {
  // The auth gate in _layout re-routes to sign-in/profile as needed.
  // 004: the home dashboard (goal/plan/progress cards) is now the
  // landing screen -- /skills stays reachable, just no longer first.
  return <Redirect href="/dashboard" />;
}
