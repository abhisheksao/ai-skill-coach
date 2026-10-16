/**
 * Google OAuth via Supabase (research R3): browser hand-off with redirect back
 * to <scheme>://auth-callback on native; standard redirect flow on web.
 * Handles both PKCE (?code=) and implicit (#access_token=) return shapes.
 *
 * Sign in with Apple (005, research.md R11) is a DIFFERENT flow entirely --
 * native `expo-apple-authentication` on iOS returns an identity token
 * directly (no browser hand-off), which Supabase's `signInWithIdToken`
 * exchanges for a session. Required by App Store review once Google
 * sign-in ships (Apple's own policy), iOS-only (the native module has no
 * web/Android counterpart).
 */
import * as AppleAuthentication from 'expo-apple-authentication';
import { makeRedirectUri } from 'expo-auth-session';
import * as QueryParams from 'expo-auth-session/build/QueryParams';
import * as WebBrowser from 'expo-web-browser';
import type { SupabaseClient } from '@supabase/supabase-js';
import { Platform } from 'react-native';

WebBrowser.maybeCompleteAuthSession();

export function createOAuth(supabase: SupabaseClient, options: { scheme: string }) {
  const redirectTo = makeRedirectUri({ scheme: options.scheme, path: 'auth-callback' });

  async function createSessionFromUrl(url: string): Promise<void> {
    const { params, errorCode } = QueryParams.getQueryParams(url);
    if (errorCode) throw new Error(errorCode);

    if (params.code) {
      const { error } = await supabase.auth.exchangeCodeForSession(params.code);
      if (error) throw error;
      return;
    }

    const { access_token, refresh_token } = params;
    if (!access_token || !refresh_token) return;
    const { error } = await supabase.auth.setSession({ access_token, refresh_token });
    if (error) throw error;
  }

  async function signInWithGoogle(): Promise<void> {
    if (Platform.OS === 'web') {
      const { error } = await supabase.auth.signInWithOAuth({ provider: 'google' });
      if (error) throw error;
      return;
    }

    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo, skipBrowserRedirect: true },
    });
    if (error) throw error;

    const result = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);
    if (result.type === 'success' && result.url) {
      await createSessionFromUrl(result.url);
    }
  }

  async function signInWithApple(): Promise<void> {
    const credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
    });
    if (!credential.identityToken) {
      throw new Error('Apple sign-in did not return an identity token');
    }
    const { error } = await supabase.auth.signInWithIdToken({
      provider: 'apple',
      token: credential.identityToken,
    });
    if (error) throw error;
  }

  return { createSessionFromUrl, signInWithGoogle, signInWithApple };
}
