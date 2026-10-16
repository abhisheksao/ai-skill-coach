import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { ApiError, getSkill, getSkillProgress, SkillDetail, SkillProgress } from '@/lib/api';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

/** Per-skill progress view (User Story 2): completed steps, streak, and
 * per-step cadence adherence — all derived server-side from CheckIn
 * records on every load (FR-004/FR-005, Constitution II), never a
 * locally cached counter. Two loads of the same skill always agree with
 * each other and with the home dashboard's card for it (SC-006, Phase
 * 7) since both read the exact same GET .../progress derivation. */
export default function Progress() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [progress, setProgress] = useState<SkillProgress | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getSkill(id), getSkillProgress(id)])
      .then(([skillDetail, progressDetail]) => {
        setSkill(skillDetail);
        setProgress(progressDetail);
      })
      .catch((error) =>
        setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal')
      );
  }, [id]);

  if (errorKey && !skill) {
    return (
      <Screen>
        <Text style={{ color: colors.error }}>{t(errorKey)}</Text>
      </Screen>
    );
  }

  if (!skill || !progress) {
    return (
      <Screen>
        <Text style={{ color: colors.textMuted }}>{t('common.loading')}</Text>
      </Screen>
    );
  }

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

      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={[styles.title, { color: colors.text }]}>{t('progress.title')}</Text>

        <View
          style={[
            styles.summaryCard,
            { backgroundColor: colors.surface, borderColor: colors.border },
          ]}
        >
          <Text style={[styles.streak, { color: colors.primary }]}>
            {t('progress.streak', { count: progress.streak_days })}
          </Text>
          <Text style={[styles.stepsComplete, { color: colors.textMuted }]}>
            {t('progress.stepsComplete', {
              completed: progress.completed_steps.length,
              total: progress.total_steps,
            })}
          </Text>
        </View>

        {skill.plan.steps.map((step) => {
          const stepProgress = progress.steps.find((s) => s.order === step.order);
          const completed = stepProgress?.completed ?? false;
          const behind = stepProgress?.behind_cadence ?? false;
          return (
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
              <Text
                style={[
                  styles.badge,
                  {
                    color: completed || behind ? colors.textOnPrimary : colors.textMuted,
                    backgroundColor: completed
                      ? colors.primary
                      : behind
                        ? colors.error
                        : colors.border,
                  },
                ]}
              >
                {completed
                  ? '✓'
                  : behind
                    ? t('progress.behindCadence')
                    : t('progress.onCadence')}
              </Text>
            </View>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: { fontSize: 32, fontWeight: '600', marginRight: spacing.md },
  badge: {
    borderRadius: 8,
    fontSize: type.caption.fontSize,
    fontWeight: '700',
    overflow: 'hidden',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  header: { alignItems: 'center', flexDirection: 'row', marginBottom: spacing.sm },
  headerTitle: { flexShrink: 1, fontSize: type.title.fontSize, fontWeight: '600' },
  scroll: { flexGrow: 1, paddingBottom: spacing.xl },
  stepBody: { flex: 1 },
  stepCadence: { fontSize: type.caption.fontSize, marginTop: spacing.xs },
  stepCard: {
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.sm,
    padding: spacing.md,
  },
  stepDescription: { fontSize: type.body.fontSize },
  stepOrder: { fontSize: type.title.fontSize, fontWeight: '700' },
  stepsComplete: { fontSize: type.body.fontSize, marginTop: spacing.xs },
  streak: { fontSize: type.display.fontSize, fontWeight: '700' },
  summaryCard: { borderRadius: 12, borderWidth: 1, marginBottom: spacing.lg, padding: spacing.md },
  title: { fontSize: type.display.fontSize, fontWeight: '700', marginBottom: spacing.md },
});
