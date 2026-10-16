import type { PushPlatform } from '@/lib/api';

/** react-native's Platform.OS -> the API's push_tokens.platform enum. */
export function resolvePushPlatform(os: string): PushPlatform {
  if (os === 'ios') return 'ios';
  if (os === 'android') return 'android';
  return 'web';
}

/** Safely reads the skill_id a push notification's `data` payload carries
 * (set server-side in notifications.py's `_send_expo_push`) -- defensive
 * against a malformed/foreign notification rather than assuming shape. */
export function extractSkillIdFromNotificationData(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const skillId = (data as Record<string, unknown>).skill_id;
  return typeof skillId === 'string' && skillId.length > 0 ? skillId : null;
}
