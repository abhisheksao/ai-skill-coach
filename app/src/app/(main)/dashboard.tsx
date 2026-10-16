import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { DuplicateSkillDialog } from '@/components/duplicate-skill-dialog';
import { PrimaryButton } from '@abhisheksao/ai-skill-coach-core/components/primary-button';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { TextField } from '@abhisheksao/ai-skill-coach-core/components/text-field';
import { ApiError, DashboardSkillCard, getDashboard, postIntentApply, UiIntent } from '@/lib/api';
import { readCachedDashboard, writeCachedDashboard } from '@/lib/dashboard-cache';
import { findDuplicate } from '@/lib/duplicate-skill';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

function stepKey(skillId: string, order: number): string {
  return `${skillId}-${order}`;
}

/** Home dashboard (User Story 6, FR-014): every skill as a card (goal +
 * plan + derived progress), the new post-sign-in landing screen
 * (index.tsx/_layout.tsx redirect target, replacing skills.tsx which
 * stays reachable). A stale card (no check-in within
 * constants.STALE_GOAL_DAYS server-side) offers continue/revise-via-
 * conversation/start-new — never delete (Constitution III/FR-017). A
 * failed refetch falls back to the last cached response with a
 * stale-data indicator (research.md R10) rather than an empty screen.
 * Each incomplete step also gets a tap-to-complete/log-partial
 * affordance (User Story 7, Phase 8) -- bypasses the LLM entirely
 * (SC-007), applied through the same validate-then-translate pipeline as
 * a conversational check-in. */
export default function Dashboard() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();

  const [skills, setSkills] = useState<DashboardSkillCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [offlineStale, setOfflineStale] = useState(false);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [duplicateMatch, setDuplicateMatch] = useState<DashboardSkillCard | null>(null);
  // Keyed by "skillId-stepOrder" -- disables just that step's buttons
  // while its apply is in flight (prevents an accidental double-fire
  // from a single tap; a genuine second tap after this clears is a
  // legitimate independent check-in, not something to dedupe).
  const [applyingStep, setApplyingStep] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const dashboard = await getDashboard();
      setSkills(dashboard.skills);
      setOfflineStale(false);
      setErrorKey(null);
      await writeCachedDashboard(dashboard);
    } catch (error) {
      const cached = await readCachedDashboard();
      if (cached) {
        setSkills(cached.skills);
        setOfflineStale(true);
      } else {
        setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal');
      }
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      setAdding(false);
      setName('');
      setLoading(true);
      fetchDashboard().finally(() => setLoading(false));
    }, [fetchDashboard])
  );

  function refresh() {
    setLoading(true); // event handler, not an effect body
    fetchDashboard().finally(() => setLoading(false));
  }

  function startWizard(skillName: string) {
    router.push({ pathname: '/wizard', params: { newSkillName: skillName } });
  }

  function openSkill(skillId: string) {
    router.push({ pathname: '/plan-review', params: { skillId } });
  }

  function reviseInConversation(skillId: string) {
    // Same nudge-into-chat path plan-review.tsx uses at the regenerate
    // cap -- no LLM call spent just to open the topic.
    router.push({ pathname: '/chat', params: { skillId, promptRevise: '1' } });
  }

  async function handleStepTap(
    skillId: string,
    stepOrder: number,
    kind: 'complete_step' | 'log_checkin'
  ) {
    const key = stepKey(skillId, stepOrder);
    setApplyingStep(key);
    try {
      const intent: UiIntent =
        kind === 'complete_step'
          ? { type: 'complete_step', step_order: stepOrder, sentiment: 'positive' }
          : { type: 'log_checkin', step_order: stepOrder, outcome: 'partial', sentiment: 'neutral' };
      await postIntentApply(skillId, intent);
      await fetchDashboard(); // dashboard + (if open) progress view update immediately
    } catch (error) {
      setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal');
    } finally {
      setApplyingStep((current) => (current === key ? null : current));
    }
  }

  function handleAdd() {
    const trimmed = name.trim();
    if (!trimmed) return;

    const duplicate = findDuplicate(
      trimmed,
      skills.map((s) => ({ id: s.skill_id, name: s.name }))
    );
    if (duplicate) {
      setDuplicateMatch(skills.find((s) => s.skill_id === duplicate.id) ?? null);
      return;
    }

    startWizard(trimmed);
  }

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.text }]}>{t('common.appName')}</Text>
        <Pressable accessibilityRole="button" onPress={() => router.push('/settings')}>
          <Text style={[styles.settingsLink, { color: colors.primary }]}>
            {t('settings.title')}
          </Text>
        </Pressable>
      </View>

      {offlineStale ? (
        <Text style={[styles.staleDataBanner, { color: colors.textMuted }]}>
          {t('dashboard.staleDataBanner')}
        </Text>
      ) : null}
      {errorKey ? <Text style={{ color: colors.error }}>{t(errorKey)}</Text> : null}

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <FlatList
          data={skills}
          keyExtractor={(item) => item.skill_id}
          refreshing={loading}
          onRefresh={refresh}
          style={styles.flex}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            !loading ? (
              <Text style={[styles.empty, { color: colors.textMuted }]}>
                {t('skills.emptyState')}
              </Text>
            ) : null
          }
          renderItem={({ item }) => (
            <View
              testID={`dashboard-card-${item.skill_id}`}
              style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
            >
              <Pressable accessibilityRole="button" onPress={() => openSkill(item.skill_id)}>
                <View style={styles.cardHeader}>
                  <Text style={[styles.cardName, { color: colors.text }]}>{item.name}</Text>
                  {item.is_stale ? (
                    <Text
                      style={[
                        styles.staleBadge,
                        { color: colors.textOnPrimary, backgroundColor: colors.error },
                      ]}
                    >
                      {t('dashboard.staleBadge')}
                    </Text>
                  ) : null}
                </View>
                <Text style={[styles.cardGoal, { color: colors.textMuted }]}>
                  {item.goal_statement}
                </Text>
                <Text style={[styles.cardMeta, { color: colors.textMuted }]}>
                  {t('progress.stepsComplete', {
                    completed: item.progress.completed_steps,
                    total: item.progress.total_steps,
                  })}
                  {' · '}
                  {t('progress.streak', { count: item.progress.streak_days })}
                </Text>
              </Pressable>

              <View style={styles.stepsList}>
                {item.steps.map((step) => {
                  const key = stepKey(item.skill_id, step.order);
                  const applying = applyingStep === key;
                  return (
                    <View key={step.order} style={styles.stepRow}>
                      <Text
                        style={[
                          styles.stepDescription,
                          { color: step.completed ? colors.textMuted : colors.text },
                        ]}
                        numberOfLines={1}
                      >
                        {step.completed ? '✓ ' : ''}
                        {step.description}
                      </Text>
                      {!step.completed ? (
                        <View style={styles.stepActions}>
                          <Pressable
                            accessibilityRole="button"
                            disabled={applying}
                            onPress={() => handleStepTap(item.skill_id, step.order, 'complete_step')}
                            style={styles.stepActionLink}
                          >
                            <Text
                              style={{
                                color: applying ? colors.textMuted : colors.primary,
                                fontSize: type.caption.fontSize,
                              }}
                            >
                              {t('dashboard.markComplete')}
                            </Text>
                          </Pressable>
                          <Pressable
                            accessibilityRole="button"
                            disabled={applying}
                            onPress={() => handleStepTap(item.skill_id, step.order, 'log_checkin')}
                            style={styles.stepActionLink}
                          >
                            <Text
                              style={{
                                color: applying ? colors.textMuted : colors.primary,
                                fontSize: type.caption.fontSize,
                              }}
                            >
                              {t('dashboard.logPartial')}
                            </Text>
                          </Pressable>
                        </View>
                      ) : null}
                    </View>
                  );
                })}
              </View>

              {item.is_stale ? (
                <View style={styles.staleActions}>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => openSkill(item.skill_id)}
                    style={styles.staleActionLink}
                  >
                    <Text style={{ color: colors.primary, fontSize: type.caption.fontSize }}>
                      {t('common.continue')}
                    </Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => reviseInConversation(item.skill_id)}
                    style={styles.staleActionLink}
                  >
                    <Text style={{ color: colors.primary, fontSize: type.caption.fontSize }}>
                      {t('dashboard.reviseAction')}
                    </Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => setAdding(true)}
                    style={styles.staleActionLink}
                  >
                    <Text style={{ color: colors.primary, fontSize: type.caption.fontSize }}>
                      {t('dashboard.startNewAction')}
                    </Text>
                  </Pressable>
                </View>
              ) : null}
            </View>
          )}
        />

        {adding ? (
          <View style={styles.addRow}>
            <View style={styles.addField}>
              <TextField
                label={t('skills.namePlaceholder')}
                value={name}
                onChangeText={setName}
                autoFocus
                maxLength={80}
              />
            </View>
            <View style={styles.addActions}>
              <Pressable onPress={() => setAdding(false)} style={styles.cancelLink}>
                <Text style={{ color: colors.textMuted, fontSize: type.body.fontSize }}>
                  {t('common.cancel')}
                </Text>
              </Pressable>
              <PrimaryButton
                label={t('common.continue')}
                onPress={handleAdd}
                disabled={!name.trim()}
              />
            </View>
          </View>
        ) : (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('skills.addSkill')}
            onPress={() => setAdding(true)}
            style={[styles.fab, { backgroundColor: colors.primary }]}
          >
            <Text style={[styles.fabLabel, { color: colors.textOnPrimary }]}>+</Text>
          </Pressable>
        )}
      </KeyboardAvoidingView>

      <DuplicateSkillDialog
        visible={!!duplicateMatch}
        name={duplicateMatch?.name ?? ''}
        onContinueExisting={() => {
          if (duplicateMatch) openSkill(duplicateMatch.skill_id);
          setDuplicateMatch(null);
        }}
        onStartNew={() => {
          const trimmed = name.trim();
          setDuplicateMatch(null);
          if (trimmed) startWizard(trimmed);
        }}
        onCancel={() => setDuplicateMatch(null)}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  addActions: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  addField: { marginBottom: spacing.sm },
  addRow: { marginTop: spacing.sm },
  cancelLink: { padding: spacing.sm },
  card: { borderRadius: 12, borderWidth: 1, marginBottom: spacing.sm, padding: spacing.md },
  cardGoal: { fontSize: type.body.fontSize, marginTop: spacing.xs },
  cardHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  cardMeta: { ...type.caption, marginTop: spacing.xs },
  cardName: { ...type.title },
  empty: { ...type.body, marginTop: spacing.xl, textAlign: 'center' },
  fab: {
    alignItems: 'center',
    alignSelf: 'flex-end',
    borderRadius: 28,
    height: 56,
    justifyContent: 'center',
    marginTop: spacing.sm,
    width: 56,
  },
  fabLabel: { fontSize: 28, fontWeight: '400', lineHeight: 32 },
  flex: { flex: 1 },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  list: { flexGrow: 1 },
  settingsLink: { ...type.body, fontWeight: '600' },
  staleActionLink: { paddingVertical: spacing.xs },
  staleActions: {
    borderTopColor: 'rgba(0,0,0,0.08)',
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
  },
  staleBadge: {
    borderRadius: 8,
    ...type.caption,
    fontWeight: '700',
    overflow: 'hidden',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  staleDataBanner: { ...type.body, marginBottom: spacing.sm, textAlign: 'center' },
  stepActionLink: { paddingLeft: spacing.sm },
  stepActions: { flexDirection: 'row' },
  stepDescription: { flex: 1, ...type.caption, paddingRight: spacing.sm },
  stepRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs,
  },
  stepsList: { marginTop: spacing.sm },
  title: { ...type.title },
});
