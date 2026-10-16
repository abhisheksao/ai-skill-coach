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
import { PrimaryButton } from '@ai-skill-coach/core/components/primary-button';
import { Screen } from '@ai-skill-coach/core/components/screen';
import { TextField } from '@ai-skill-coach/core/components/text-field';
import { ApiError, getSkills, SkillSummary } from '@/lib/api';
import { findDuplicate } from '@/lib/duplicate-skill';
import { spacing, type, useTheme } from '@ai-skill-coach/core/theme';

/** Skill list (User Story 3): cards + "Add skill" entry with a
 * client-side duplicate-name warning (FR-012, research R2/R9) -- no LLM
 * call spent on this check. Tapping a card opens the skill's plan/goal
 * detail (not chat directly) -- there was previously no way back to the
 * plan once you left the initial post-wizard review. Superseded as the
 * post-sign-in landing screen by dashboard.tsx (004, User Story 6) --
 * this route stays reachable, just no longer the first thing a signed-in
 * user sees. */

export default function Skills() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();

  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [duplicateMatch, setDuplicateMatch] = useState<SkillSummary | null>(null);

  const fetchSkills = useCallback(() => {
    return getSkills()
      .then(setSkills)
      .catch((error) =>
        setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal')
      );
  }, []);

  // Refetch AND reset the add-skill UI every time this screen regains
  // focus -- fixes a real bug: returning here after starting a wizard left
  // the previous skill's name still sitting in the (still-open) text field.
  useFocusEffect(
    useCallback(() => {
      setAdding(false);
      setName('');
      fetchSkills().finally(() => setLoading(false));
    }, [fetchSkills])
  );

  function refresh() {
    setLoading(true); // fine here: event handler, not an effect body
    fetchSkills().finally(() => setLoading(false));
  }

  function startWizard(skillName: string) {
    router.push({ pathname: '/wizard', params: { newSkillName: skillName } });
  }

  function openSkill(skillId: string) {
    router.push({ pathname: '/plan-review', params: { skillId } });
  }

  function handleAdd() {
    const trimmed = name.trim();
    if (!trimmed) return;

    const duplicate = findDuplicate(trimmed, skills);
    if (duplicate) {
      setDuplicateMatch(duplicate);
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

      {errorKey ? <Text style={{ color: colors.error }}>{t(errorKey)}</Text> : null}

      {/* The whole scrollable body + footer share one KeyboardAvoidingView
       * (not just the add-row) so that on Android, "height" behavior
       * actually has flex:1 content above it to shrink -- wrapping only
       * the small footer left it with nothing to compress, so the keyboard
       * still covered the field. */}
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <FlatList
          data={skills}
          keyExtractor={(item) => item.id}
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
            <Pressable
              accessibilityRole="button"
              onPress={() => openSkill(item.id)}
              style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
            >
              <Text style={[styles.cardName, { color: colors.text }]}>{item.name}</Text>
              <Text style={[styles.cardGoal, { color: colors.textMuted }]}>
                {item.goal_statement}
              </Text>
              <Text style={[styles.cardMeta, { color: colors.textMuted }]}>
                {item.step_count} steps · {item.target_date}
              </Text>
            </Pressable>
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
          if (duplicateMatch) openSkill(duplicateMatch.id);
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
  cardGoal: { ...type.body, marginTop: spacing.xs },
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
  title: { ...type.title },
});
