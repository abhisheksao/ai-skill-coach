import { useTranslation } from 'react-i18next';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

type Props = {
  visible: boolean;
  name: string;
  onContinueExisting: () => void;
  onStartNew: () => void;
  onCancel: () => void;
};

/** Cross-platform replacement for `Alert.alert`'s 3-button prompt --
 * react-native-web's Alert.alert is a no-op stub (confirmed: no
 * window.alert/confirm fallback), so the duplicate-skill warning never
 * appeared on web at all before this. Native keeps the same copy/options. */
export function DuplicateSkillDialog({
  visible,
  name,
  onContinueExisting,
  onStartNew,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.backdrop}>
        <View style={[styles.card, { backgroundColor: colors.surface }]}>
          <Text style={[styles.title, { color: colors.text }]}>{t('skills.duplicateTitle')}</Text>
          <Text style={[styles.body, { color: colors.textMuted }]}>
            {t('skills.duplicateBody', { name })}
          </Text>

          <Pressable accessibilityRole="button" onPress={onContinueExisting} style={styles.option}>
            <Text style={[styles.optionLabel, { color: colors.primary }]}>
              {t('skills.duplicateContinue')}
            </Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={onStartNew} style={styles.option}>
            <Text style={[styles.optionLabel, { color: colors.primary }]}>
              {t('skills.duplicateNew')}
            </Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={onCancel} style={styles.option}>
            <Text style={[styles.optionLabel, { color: colors.textMuted }]}>
              {t('common.cancel')}
            </Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    backgroundColor: 'rgba(0,0,0,0.4)',
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
  },
  body: { fontSize: type.body.fontSize, marginBottom: spacing.md },
  card: { borderRadius: 16, padding: spacing.lg },
  option: { paddingVertical: spacing.sm },
  optionLabel: { fontSize: type.body.fontSize, fontWeight: '600', textAlign: 'center' },
  title: { fontSize: type.title.fontSize, fontWeight: '600', marginBottom: spacing.xs },
});
