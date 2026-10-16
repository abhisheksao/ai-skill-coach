import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { lineHeight, spacing, type, useTheme } from '../theme/tokens';

type Props = {
  content: string;
  sender: 'user' | 'assistant';
  /** V4 (005, research.md R9): a message that failed to send while
   * offline stays visible with a retry affordance, instead of vanishing. */
  status?: 'sent' | 'failed';
  onRetry?: () => void;
};

/** Design rule: user bubbles = primary/on-primary; coach bubbles = surface/text.
 *  Identical in chat and voice modes (Constitution IV). */
export function ChatBubble({ content, sender, status, onRetry }: Props) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const isUser = sender === 'user';
  return (
    <View style={status === 'failed' ? styles.failedWrap : undefined}>
      <View
        style={[
          styles.bubble,
          isUser
            ? { alignSelf: 'flex-end', backgroundColor: colors.primary }
            : {
                alignSelf: 'flex-start',
                backgroundColor: colors.surface,
                borderColor: colors.border,
                borderWidth: StyleSheet.hairlineWidth,
              },
          status === 'failed' ? { opacity: 0.7 } : null,
        ]}
      >
        <Text style={[styles.text, { color: isUser ? colors.textOnPrimary : colors.text }]}>
          {content}
        </Text>
      </View>
      {status === 'failed' ? (
        <View style={styles.failedRow}>
          <Text style={[styles.failedLabel, { color: colors.error }]}>
            {t('chat.sendFailed')}
          </Text>
          <Pressable accessibilityRole="button" onPress={onRetry}>
            <Text style={[styles.retryLabel, { color: colors.primary }]}>
              {t('chat.retrySend')}
            </Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    borderRadius: 16,
    marginVertical: spacing.xs,
    maxWidth: '82%',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  failedLabel: { fontSize: type.caption.fontSize },
  failedRow: {
    alignItems: 'center',
    alignSelf: 'flex-end',
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  failedWrap: { alignItems: 'flex-end' },
  retryLabel: { fontSize: type.caption.fontSize, fontWeight: '600' },
  text: { fontSize: type.body.fontSize, lineHeight: lineHeight.body },
});
