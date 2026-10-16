import { useLocalSearchParams, useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ConversationView } from '@/components/conversation-view';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { useChatSession } from '@/hooks/use-chat-session';
import { useAuth } from '@/lib/auth-context';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

/** Wizard onboarding (User Story 1): no skill exists yet. Reuses the same
 * conversation UI/pipeline as ongoing chat (Constitution IV) -- the only
 * difference is skillId starts null and newSkillName is sent. Once the
 * server resolves a skill_id (create_skill applied), navigate to the plan
 * review screen (research R3: the plan is already persisted by then). */
export default function Wizard() {
  const { colors } = useTheme();
  const router = useRouter();
  const { profile } = useAuth();
  const { newSkillName } = useLocalSearchParams<{ newSkillName: string }>();

  const { messages, draft, setDraft, send, retry, sending, errorKey, suggestedReplies } =
    useChatSession({
      newSkillName,
      onSkillResolved: (skillId) =>
        router.replace({ pathname: '/plan-review', params: { skillId } }),
    });

  return (
    <Screen>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => router.back()}>
          <Text style={[styles.back, { color: colors.primary }]}>‹</Text>
        </Pressable>
        <Text style={[styles.title, { color: colors.text }]} numberOfLines={1}>
          {newSkillName}
        </Text>
      </View>

      <ConversationView
        messages={messages}
        draft={draft}
        onDraftChange={setDraft}
        onSend={send}
        onRetry={retry}
        sending={sending}
        errorKey={errorKey}
        emptyStateKey="skills.namePlaceholder"
        suggestedReplies={suggestedReplies}
        voiceLanguage={profile?.language}
        voiceRepliesEnabled={profile?.voice_replies_enabled}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: { fontSize: 32, fontWeight: '600', marginRight: spacing.md },
  header: { alignItems: 'center', flexDirection: 'row', marginBottom: spacing.sm },
  title: { flexShrink: 1, ...type.title },
});
