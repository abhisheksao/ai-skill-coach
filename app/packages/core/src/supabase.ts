/**
 * Supabase client with persistent sessions.
 *
 * Session storage is AsyncStorage per Supabase's official Expo guidance
 * (research R12): session JSON regularly exceeds expo-secure-store's 2048-byte
 * Android limit. Auth tokens are short-lived JWTs.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { AppState, Platform } from 'react-native';

export function createSupabaseClient(supabaseUrl: string, supabaseAnonKey: string) {
  const isWeb = Platform.OS === 'web';

  const supabase = createClient(
    supabaseUrl || 'http://localhost:54321',
    supabaseAnonKey || 'missing-anon-key',
    {
      auth: {
        ...(isWeb ? {} : { storage: AsyncStorage }),
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: isWeb,
      },
    }
  );

  // Refresh tokens only while the app is foregrounded (Supabase Expo guidance).
  if (!isWeb) {
    AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        supabase.auth.startAutoRefresh();
      } else {
        supabase.auth.stopAutoRefresh();
      }
    });
  }

  return supabase;
}
