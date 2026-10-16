import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { PrimaryButton } from '@abhisheksao/ai-skill-coach-core/components/primary-button';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { TextField } from '@abhisheksao/ai-skill-coach-core/components/text-field';
import { ApiError, getSkill, postRegenerate, RegenerateReason, SkillDetail } from '@/lib/api';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

const REASONS: RegenerateReason[] = ['too_much', 'too_easy', 'not_quite_right'];
const MAX_REGENERATIONS = 3;

/** Skill detail: goal + plan + steps (User Story 2/3). Reached both right
 * after the wizard completes AND from tapping a skill card on the home
 * screen (there was previously no way to see a plan again once you left
 * the initial review) -- the plan is already persisted either way
 * (research R3), so this always reads recorded state (FR-007), never an
 * unsaved draft. "Chat about this skill" opens the ongoing conversation.
 * Regenerate requires a reason (FR-011); at the 3-attempt cap the server
 * returns 409 and this screen routes into chat.tsx with a revision nudge
 * (T018) instead of offering a 4th regeneration. */
export default function PlanReview() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  const { skillId } = useLocalSearchParams<{ skillId: string }>();

  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [pickingReason, setPickingReason] = useState(false);
  const [reason, setReason] = useState<RegenerateReason | null>(null);
  const [note, setNote] = useState('');
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    getSkill(skillId)
      .then(setSkill)
      .catch((error) => setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal'));
  }, [skillId]);

  function openChat() {
    router.push({ pathname: '/chat', params: { skillId } });
  }

  function openProgress() {
    router.push({ pathname: '/skill/[id]/progress', params: { id: skillId } });
  }

  async function submitRegenerate() {
    if (!reason) return;
    setRegenerating(true);
    setErrorKey(null);
    try {
      const result = await postRegenerate(skillId, reason, note.trim() || undefined);
      setSkill((prev) => (prev ? { ...prev, plan: result.plan } : prev));
      setPickingReason(false);
      setReason(null);
      setNote('');
    } catch (error) {
      if (error instanceof ApiError && error.code === 'regeneration_cap_reached') {
        // T018: cap reached -- into an ordinary conversation on this
        // skill, primed with a locally-rendered nudge (no LLM call spent
        // just to open the topic).
        router.replace({ pathname: '/chat', params: { skillId, promptRevise: '1' } });
        return;
      }
      setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal');
    } finally {
      setRegenerating(false);
    }
  }

  if (errorKey && !skill) {
    return (
      <Screen>
        <Text style={{ color: colors.error }}>{t(errorKey)}</Text>
      </Screen>
    );
  }

  if (!skill) {
    return (
      <Screen>
        <Text style={{ color: colors.textMuted }}>{t('common.loading')}</Text>
      </Screen>
    );
  }

  const canRegenerate = skill.plan.generation < MAX_REGENERATIONS;

  return (
    <Screen>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" onPress={() => router.push('/dashboard')}>
          <Text style={[styles.back, { color: colors.primary }]}>‹</Text>
        </Pressable>
        <Text style={[styles.headerTitle, { color: colors.text }]} numberOfLines={1}>
          {skill.name}
        </Text>
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={[styles.title, { color: colors.text }]}>{t('plan.title')}</Text>
          <Text style={[styles.goal, { color: colors.text }]}>{skill.goal.statement}</Text>
          <Text style={[styles.targetDate, { color: colors.textMuted }]}>
            {skill.goal.target_date}
          </Text>

          {skill.plan.steps.map((step) => (
            <View
              key={step.order}
              style={[
                styles.stepCard,
                { backgroundColor: colors.surface, borderColor: colors.border },
              ]}
            >
              <Text style={[styles.stepOrder, { color: colors.primary }]}>{step.order}</Text>
              <View style={styles.stepBody}>
                <Text style={[styles.stepDescription, { color: colors.text }]}>
                  {step.description}
                </Text>
                <Text style={[styles.stepCadence, { color: colors.textMuted }]}>
                  {step.cadence_per_week}x/week
                </Text>
              </View>
            </View>
          ))}

          {errorKey ? (
            <Text style={[styles.error, { color: colors.error }]}>{t(errorKey)}</Text>
          ) : null}

          <PrimaryButton label={t('plan.chatButton')} onPress={openChat} />
          <Pressable
            accessibilityRole="button"
            onPress={openProgress}
            style={styles.progressLink}
          >
            <Text style={{ color: colors.primary, fontSize: type.body.fontSize }}>
              {t('progress.viewLink')}
            </Text>
          </Pressable>

          {canRegenerate ? (
            pickingReason ? (
              <View style={styles.regenerateBox}>
                <Text style={[styles.regenerateTitle, { color: colors.text }]}>
                  {t('plan.regenerate.title')}
                </Text>
                <View style={styles.reasonRow}>
                  {REASONS.map((option) => {
                    const selected = option === reason;
                    return (
                      <Pressable
                        key={option}
                        accessibilityRole="radio"
                        accessibilityState={{ selected }}
                        onPress={() => setReason(option)}
                        style={[
                          styles.reasonChip,
                          {
                            backgroundColor: selected ? colors.primary : colors.surface,
                            borderColor: selected ? colors.primary : colors.border,
                          },
                        ]}
                      >
                        <Text
                          style={{
                            color: selected ? colors.textOnPrimary : colors.text,
                            fontSize: type.body.fontSize,
                            fontWeight: selected ? '600' : '400',
                          }}
                        >
                          {t(`plan.regenerate.${camel(option)}`)}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
                <TextField
                  label={t('plan.regenerate.notePlaceholder')}
                  value={note}
                  onChangeText={setNote}
                  maxLength={200}
                />
                <PrimaryButton
                  label={t('plan.regenerate.submit')}
                  onPress={submitRegenerate}
                  disabled={!reason}
                  loading={regenerating}
                />
              </View>
            ) : (
              <Pressable onPress={() => setPickingReason(true)} style={styles.revealLink}>
                <Text style={{ color: colors.primary, fontSize: type.body.fontSize }}>
                  {t('plan.regenerate.title')}
                </Text>
              </Pressable>
            )
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function camel(reason: RegenerateReason): string {
  return reason.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
}

const styles = StyleSheet.create({
  back: { fontSize: 32, fontWeight: '600', marginRight: spacing.md },
  error: { marginBottom: spacing.sm, textAlign: 'center' },
  flex: { flex: 1 },
  goal: { fontSize: type.title.fontSize, fontWeight: '600', marginBottom: spacing.xs },
  header: { alignItems: 'center', flexDirection: 'row', marginBottom: spacing.sm },
  headerTitle: { flexShrink: 1, fontSize: type.title.fontSize, fontWeight: '600' },
  progressLink: { alignItems: 'center', marginTop: spacing.md },
  reasonChip: {
    borderRadius: 20,
    borderWidth: 1,
    marginBottom: spacing.sm,
    marginRight: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  reasonRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: spacing.sm },
  regenerateBox: { marginTop: spacing.lg },
  regenerateTitle: { fontSize: type.body.fontSize, fontWeight: '600' },
  revealLink: { alignItems: 'center', marginTop: spacing.lg },
  scroll: { flexGrow: 1, paddingBottom: spacing.xl },
  stepBody: { flex: 1 },
  stepCadence: { fontSize: type.caption.fontSize, marginTop: spacing.xs },
  stepCard: {
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.sm,
    padding: spacing.md,
  },
  stepDescription: { fontSize: type.body.fontSize },
  stepOrder: { fontSize: type.title.fontSize, fontWeight: '700' },
  targetDate: { fontSize: type.body.fontSize, marginBottom: spacing.lg },
  title: { fontSize: type.display.fontSize, fontWeight: '700', marginBottom: spacing.md },
});
