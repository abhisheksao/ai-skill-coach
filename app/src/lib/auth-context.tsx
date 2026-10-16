/**
 * Session + profile state for the auth gate (T015).
 * Profile presence decides onboarding routing; its language drives i18n.
 */
import type { Session } from '@supabase/supabase-js';
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';

import { setAppLanguage } from '@/i18n';
import { fetchOwnProfile, Profile, supabase } from '@/lib/supabase';

type AuthState = {
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  refreshProfile: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  session: null,
  profile: null,
  loading: true,
  refreshProfile: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async (activeSession: Session | null) => {
    if (!activeSession) {
      setProfile(null);
      return;
    }
    const fetched = await fetchOwnProfile(activeSession.user.id);
    setProfile(fetched);
    if (fetched) {
      setAppLanguage(fetched.language);
    }
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      setSession(data.session);
      await loadProfile(data.session);
      setLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange(
      async (_event, nextSession) => {
        setSession(nextSession);
        await loadProfile(nextSession);
        setLoading(false);
      }
    );
    return () => subscription.subscription.unsubscribe();
  }, [loadProfile]);

  const refreshProfile = useCallback(async () => loadProfile(session), [loadProfile, session]);

  return (
    <AuthContext.Provider value={{ session, profile, loading, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
