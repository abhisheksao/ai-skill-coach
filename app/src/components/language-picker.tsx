import { Pressable, StyleSheet, Text, View } from 'react-native';

import { SupportedLanguage } from '@/i18n';
import { type, useTheme } from '@ai-skill-coach/core/theme';

const LANGUAGES: { code: SupportedLanguage; native: string }[] = [
  { code: 'en', native: 'English' },
  { code: 'hi', native: 'हिन्दी' },
  { code: 'es', native: 'Español' },
  { code: 'fr', native: 'Français' },
  { code: 'de', native: 'Deutsch' },
];

type Props = {
  value: SupportedLanguage;
  onChange: (code: SupportedLanguage) => void;
};

export function LanguagePicker({ value, onChange }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.list}>
      {LANGUAGES.map(({ code, native }) => {
        const selected = code === value;
        return (
          <Pressable
            key={code}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            onPress={() => onChange(code)}
            style={[
              styles.chip,
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
              {native}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: 20,
    borderWidth: 1,
    marginBottom: 8,
    marginRight: 8,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  list: { flexDirection: 'row', flexWrap: 'wrap' },
});
