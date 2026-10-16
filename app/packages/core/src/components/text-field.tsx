import { StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';

import { spacing, type, useTheme } from '../theme/tokens';

type Props = TextInputProps & {
  label: string;
  errorText?: string | null;
};

export function TextField({ label, errorText, ...inputProps }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <Text style={[styles.label, { color: colors.textMuted }]}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.textMuted}
        style={[
          styles.input,
          {
            backgroundColor: colors.surface,
            borderColor: errorText ? colors.error : colors.border,
            color: colors.text,
          },
        ]}
        {...inputProps}
      />
      {errorText ? <Text style={[styles.error, { color: colors.error }]}>{errorText}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  error: { fontSize: type.caption.fontSize, marginTop: spacing.xs },
  input: {
    borderRadius: 12,
    borderWidth: 1,
    fontSize: type.body.fontSize,
    minHeight: 48,
    paddingHorizontal: spacing.md,
  },
  label: { fontSize: type.caption.fontSize, marginBottom: spacing.xs },
  wrap: { marginBottom: spacing.md },
});
