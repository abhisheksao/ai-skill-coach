/**
 * Typed client for the Skill Coach API. Errors carry the server's i18n
 * message_key (contracts/api.md) so screens can render them localized.
 */
import { ApiError, createApiClient } from '@abhisheksao/ai-skill-coach-core/api-client';

import { supabase } from '@/lib/supabase';

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? '';

export { ApiError };

const { request, requestVoid } = createApiClient(supabase, API_URL);

export type ChatResult = {
  reply: string;
  session_id: string;
  skill_id: string | null;
  intents: unknown[];
  suggested_replies: string[];
  /** 005, contracts/api.md R2: additive, absent on every normal turn.
   * `resets_at` is null for the kill-switch case (no automatic reset). */
  budget?: { exhausted: boolean; resets_at: string | null } | null;
};

function post<T>(path: string, body: object): Promise<T> {
  return request<T>('POST', path, body);
}

export type Modality = 'chat' | 'voice';

export function postChat(
  message: string,
  sessionId: string,
  options?: { skillId?: string | null; newSkillName?: string; modality?: Modality }
): Promise<ChatResult> {
  return post<ChatResult>('/v1/chat', {
    message,
    session_id: sessionId,
    ...(options?.skillId ? { skill_id: options.skillId } : {}),
    ...(options?.newSkillName ? { new_skill_name: options.newSkillName } : {}),
    ...(options?.modality ? { modality: options.modality } : {}),
  });
}

export type ProfilePayload = {
  display_name: string | null;
  language: string;
  timezone: string;
  consent: true;
  voice_replies_enabled: boolean;
};

export function postProfile(payload: ProfilePayload): Promise<{ profile: object }> {
  return post<{ profile: object }>('/v1/profile', payload);
}

export type SkillSummary = {
  id: string;
  name: string;
  created_at: string;
  goal_statement: string;
  target_date: string;
  step_count: number;
};

export async function getSkills(): Promise<SkillSummary[]> {
  const result = await request<{ skills: SkillSummary[] }>('GET', '/v1/skills');
  return result.skills;
}

export type StepDetail = { order: number; description: string; cadence_per_week: number };

export type SkillDetail = {
  id: string;
  name: string;
  goal: { statement: string; target_date: string };
  plan: { id: string; generation: number; steps: StepDetail[] };
};

export function getSkill(skillId: string): Promise<SkillDetail> {
  return request<SkillDetail>('GET', `/v1/skills/${skillId}`);
}

export type StepProgress = {
  order: number;
  completed: boolean;
  behind_cadence: boolean;
  last_checkin_at: string | null;
};

export type SkillProgress = {
  skill_id: string;
  completed_steps: number[];
  total_steps: number;
  streak_days: number;
  steps: StepProgress[];
};

/** Recomputed server-side from CheckIn records on every call (FR-004,
 * Constitution II) -- never a locally cached value. */
export function getSkillProgress(skillId: string): Promise<SkillProgress> {
  return request<SkillProgress>('GET', `/v1/skills/${skillId}/progress`);
}

export type DashboardStepCard = {
  order: number;
  description: string;
  completed: boolean;
  behind_cadence: boolean;
};

export type DashboardSkillCard = {
  skill_id: string;
  name: string;
  goal_statement: string;
  target_date: string;
  is_stale: boolean;
  progress: { completed_steps: number; total_steps: number; streak_days: number };
  steps: DashboardStepCard[];
};

export type DashboardResponse = { skills: DashboardSkillCard[] };

/** Home dashboard (User Story 6) -- same derivation as getSkillProgress,
 * composed per-skill (SC-006: the two always agree). */
export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>('GET', '/v1/dashboard');
}

export type UiIntent =
  | { type: 'complete_step'; step_order: number; sentiment: 'positive' | 'neutral' | 'negative' }
  | {
      type: 'log_checkin';
      step_order: number;
      outcome: 'partial';
      sentiment: 'positive' | 'neutral' | 'negative';
    };

export type ApplyIntentResult = { checkin_id: string; applied_at: string };

/** UI-native tap-to-complete/log-partial (User Story 7) -- bypasses the
 * LLM entirely (SC-007); source is always forced to "ui_tap" server-side
 * (FR-016), never sent from here. */
export function postIntentApply(skillId: string, intent: UiIntent): Promise<ApplyIntentResult> {
  return post<ApplyIntentResult>('/v1/intents/apply', { skill_id: skillId, intent });
}

export type RegenerateReason = 'too_much' | 'too_easy' | 'not_quite_right';

export type RegenerateResult = {
  reply: string;
  plan: SkillDetail['plan'];
};

export function postRegenerate(
  skillId: string,
  reason: RegenerateReason,
  note?: string
): Promise<RegenerateResult> {
  return post<RegenerateResult>(`/v1/skills/${skillId}/plan/regenerate`, {
    reason,
    ...(note ? { note } : {}),
  });
}

export type PushPlatform = 'ios' | 'android' | 'web';

/** Upserts on (user, token) server-side -- safe to call again with the
 * same token on every foreground, and covers platform-rotated tokens too
 * (FR-013, no separate "refresh" endpoint). */
export function postPushToken(token: string, platform: PushPlatform): Promise<void> {
  return requestVoid('POST', '/v1/push-tokens', { token, platform });
}

/** Idempotent -- revoking an already-revoked or unknown token is not an
 * error (FR-013, sign-out). */
export function deletePushToken(token: string): Promise<void> {
  return requestVoid('DELETE', '/v1/push-tokens', { token });
}
