/**
 * The app's Supabase client (env-configured; see @abhisheksao/ai-skill-coach-core/supabase).
 *
 * Session storage is AsyncStorage per Supabase's official Expo guidance
 * (research R12): session JSON regularly exceeds expo-secure-store's 2048-byte
 * Android limit. Auth tokens are short-lived JWTs; storage hardening is
 * revisited in feature 005.
 */
import { createSupabaseClient } from '@abhisheksao/ai-skill-coach-core/supabase';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '';

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    'Supabase env missing: set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY (app/.env)'
  );
}

export const supabase = createSupabaseClient(supabaseUrl, supabaseAnonKey);

export type Profile = {
  user_id: string;
  display_name: string | null;
  language: 'en' | 'hi' | 'es' | 'fr' | 'de';
  timezone: string;
  consent_at: string;
  voice_replies_enabled: boolean;
};

/** Own row under RLS; null when the profile step hasn't been completed. */
export async function fetchOwnProfile(userId: string): Promise<Profile | null> {
  const { data, error } = await supabase
    .from('profiles')
    .select('user_id, display_name, language, timezone, consent_at, voice_replies_enabled')
    .eq('user_id', userId)
    .maybeSingle();
  if (error) {
    console.warn('profiles fetch failed:', error.message);
    return null;
  }
  return data as Profile | null;
}
