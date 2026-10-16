/** The app's OAuth flows, bound to its Supabase client and URL scheme. */
import { createOAuth } from '@abhisheksao/ai-skill-coach-core/oauth';

import { supabase } from '@/lib/supabase';

export const { createSessionFromUrl, signInWithGoogle, signInWithApple } = createOAuth(supabase, {
  scheme: 'skillcoach',
});
