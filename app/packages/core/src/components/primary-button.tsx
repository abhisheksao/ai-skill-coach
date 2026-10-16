import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { spacing, type, useTheme } from '../theme/tokens';

type Props = {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  testID?: string;
};

export function PrimaryButton({ label, onPress, disabled, loading, testID }: Props) {
  const { colors } = useTheme();
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={inactive}
      testID={testID}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: pressed ? colors.primaryPressed : colors.primary },
        inactive && styles.disabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={colors.textOnPrimary} />
      ) : (
        <Text style={[styles.label, { color: colors.textOnPrimary }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    borderRadius: 12,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 4,
  },
  disabled: { opacity: 0.5 },
  label: { ...type.body, fontWeight: '600' },
});
