import * as Crypto from 'expo-crypto';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ConversationView } from '@/components/conversation-view';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { useChatSession } from '@/hooks/use-chat-session';
import { useAuth } from '@/lib/auth-context';
import { supabase } from '@/lib/supabase';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

/** Ongoing conversation for one skill (?skillId=...), or, if no skillId is
 * present, a general chat (pre-002 behavior, kept for direct navigation).
 * ?promptRevise=1 (T018, cap-reached routing from plan-review) appends a
 * local, non-persisted nudge bubble inviting the user to revise their
 * goal/timeline -- no LLM call spent just to open the topic. */
export default function Chat() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const { session, profile } = useAuth();
  const router = useRouter();
  const { skillId, promptRevise } = useLocalSearchParams<{
    skillId?: string;
    promptRevise?: string;
  }>();

  const {
    messages,
    setMessages,
    draft,
    setDraft,
    send,
    retry,
    sending,
    errorKey,
    suggestedReplies,
  } = useChatSession({ skillId: skillId ?? null });

  // History: own rows via RLS, scoped to this skill so conversations never
  // bleed across skills (User Story 3) — oldest first (FR-005).
  // Keyed on the user, not the session object: that is replaced on every
  // token refresh, which would needlessly re-run this mid-conversation.
  const userId = session?.user.id;
  useEffect(() => {
    if (!userId) return;
    setMessages([]); // a skill switch must not carry the old transcript (User Story 3)
    let query = supabase
      .from('messages')
      .select('id, sender, content')
      .order('created_at', { ascending: true })
      .limit(200);
    query = skillId ? query.eq('skill_id', skillId) : query.is('skill_id', null);
    let cancelled = false;
    query.then(({ data, error }) => {
      if (cancelled) return; // a stale response from the previous skill/session
      const loaded = !error && data ? (data as typeof messages) : [];
      const nudge = promptRevise
        ? [
            {
              id: Crypto.randomUUID(),
              sender: 'assistant' as const,
              content: t('plan.regenerate.capReachedTitle'),
            },
          ]
        : [];
      // Prepend history, don't replace: anything sent while it was loading
      // (incl. a V4 failed/unsent message) must survive. The query is issued
      // before the user can send, so its snapshot never holds those.
      setMessages((prev) => [...loaded, ...nudge, ...prev]);
    });
    return () => {
      cancelled = true;
    };
    // promptRevise/t intentionally excluded: including them would re-run
    // this on every render where `t`'s reference changes (e.g. a language
    // switch) and re-append the nudge bubble. This should fire once per
    // skillId/user only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, skillId, setMessages]);

  return (
    <Screen>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => router.push('/dashboard')}>
          <Text style={[styles.back, { color: colors.primary }]}>‹</Text>
        </Pressable>
        <Text style={[styles.title, { color: colors.text }]}>{t('common.appName')}</Text>
        <Pressable accessibilityRole="button" onPress={() => router.push('/settings')}>
          <Text style={[styles.settingsLink, { color: colors.primary }]}>
            {t('settings.title')}
          </Text>
        </Pressable>
      </View>

      <ConversationView
        messages={messages}
        draft={draft}
        onDraftChange={setDraft}
        onSend={send}
        onRetry={retry}
        sending={sending}
        errorKey={errorKey}
        suggestedReplies={suggestedReplies}
        voiceLanguage={profile?.language}
        voiceRepliesEnabled={profile?.voice_replies_enabled}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: { fontSize: 32, fontWeight: '600' },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  settingsLink: { ...type.body, fontWeight: '600' },
  title: { ...type.title },
});
