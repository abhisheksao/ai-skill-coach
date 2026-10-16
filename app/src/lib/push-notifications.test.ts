import { extractSkillIdFromNotificationData, resolvePushPlatform } from './push-notifications';

describe('resolvePushPlatform', () => {
  it('maps ios and android through unchanged', () => {
    expect(resolvePushPlatform('ios')).toBe('ios');
    expect(resolvePushPlatform('android')).toBe('android');
  });

  it('falls back to web for anything else', () => {
    expect(resolvePushPlatform('windows')).toBe('web');
    expect(resolvePushPlatform('web')).toBe('web');
  });
});

describe('extractSkillIdFromNotificationData', () => {
  it('extracts a string skill_id', () => {
    expect(extractSkillIdFromNotificationData({ skill_id: 'skill-1' })).toBe('skill-1');
  });

  it('returns null for missing data', () => {
    expect(extractSkillIdFromNotificationData(null)).toBeNull();
    expect(extractSkillIdFromNotificationData(undefined)).toBeNull();
  });

  it('returns null when skill_id is absent or empty', () => {
    expect(extractSkillIdFromNotificationData({})).toBeNull();
    expect(extractSkillIdFromNotificationData({ skill_id: '' })).toBeNull();
  });

  it('returns null for a malformed/foreign payload rather than throwing', () => {
    expect(extractSkillIdFromNotificationData('not-an-object')).toBeNull();
    expect(extractSkillIdFromNotificationData({ skill_id: 42 })).toBeNull();
  });
});
