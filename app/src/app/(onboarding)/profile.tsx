import * as Localization from 'expo-localization';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { LanguagePicker } from '@/components/language-picker';
import { PrimaryButton } from '@ai-skill-coach/core/components/primary-button';
import { Screen } from '@ai-skill-coach/core/components/screen';
import { TextField } from '@ai-skill-coach/core/components/text-field';
import { deviceLanguage, setAppLanguage, SupportedLanguage } from '@/i18n';
import { ApiError, postProfile } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { supabase } from '@/lib/supabase';
import { spacing, type, useTheme } from '@ai-skill-coach/core/theme';

const POLICY_URL = process.env.EXPO_PUBLIC_POLICY_URL ?? 'https://example.com/skillcoach-policy';

/** Post-signup profile step (T030 / FR-010..012): explicit language picker
 *  pre-selected from the device locale, optional display name, consent.
 *  Both fields remain editable later in Settings (FR-011). */
export default function ProfileStep() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const { refreshProfile } = useAuth();

  const [language, setLanguage] = useState<SupportedLanguage>(deviceLanguage());
  const [displayName, setDisplayName] = useState('');
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  function pickLanguage(code: SupportedLanguage) {
    setLanguage(code);
    setAppLanguage(code); // the step itself re-renders in the picked language
  }

  async function submit() {
    setSaving(true);
    setErrorKey(null);
    try {
      await postProfile({
        display_name: displayName.trim() || null,
        language,
        timezone: Localization.getCalendars()[0]?.timeZone ?? 'UTC',
        consent: true,
        voice_replies_enabled: true, // FR-004 default; changeable later in Settings
      });
      await refreshProfile(); // auth gate routes to chat
    } catch (error) {
      setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={[styles.title, { color: colors.text }]}>{t('profile.title')}</Text>
        <Text style={[styles.subtitle, { color: colors.textMuted }]}>
          {t('profile.subtitle')}
        </Text>

        <Text style={[styles.label, { color: colors.textMuted }]}>{t('profile.language')}</Text>
        <LanguagePicker value={language} onChange={pickLanguage} />

        <TextField
          label={t('profile.displayName')}
          value={displayName}
          onChangeText={setDisplayName}
          maxLength={60}
        />

        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: consent }}
          onPress={() => setConsent((c) => !c)}
          style={styles.consentRow}
        >
          <View
            style={[
              styles.checkbox,
              {
                backgroundColor: consent ? colors.primary : colors.surface,
                borderColor: consent ? colors.primary : colors.border,
              },
            ]}
          >
            {consent ? (
              <Text style={{ color: colors.textOnPrimary, fontWeight: '700' }}>✓</Text>
            ) : null}
          </View>
          <Text style={[styles.consentText, { color: colors.text }]}>{t('profile.consent')}</Text>
        </Pressable>

        <Pressable
          accessibilityRole="link"
          onPress={() => WebBrowser.openBrowserAsync(POLICY_URL)}
        >
          <Text style={[styles.policyLink, { color: colors.primary }]}>
            {t('profile.viewPolicy')}
          </Text>
        </Pressable>

        {errorKey ? (
          <Text style={[styles.error, { color: colors.error }]}>{t(errorKey)}</Text>
        ) : null}

        <PrimaryButton
          label={t('common.continue')}
          onPress={submit}
          disabled={!consent}
          loading={saving}
        />

        <Pressable
          accessibilityRole="button"
          onPress={() => supabase.auth.signOut()}
          style={styles.signOut}
        >
          <Text style={[styles.signOutText, { color: colors.textMuted }]}>
            {t('auth.signOut')}
          </Text>
        </Pressable>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  checkbox: {
    alignItems: 'center',
    borderRadius: 6,
    borderWidth: 1.5,
    height: 24,
    justifyContent: 'center',
    marginRight: spacing.sm,
    width: 24,
  },
  consentRow: { alignItems: 'center', flexDirection: 'row', marginBottom: spacing.sm },
  consentText: { flex: 1, fontSize: type.body.fontSize },
  error: { marginBottom: spacing.sm, textAlign: 'center' },
  label: { fontSize: type.caption.fontSize, marginBottom: spacing.xs },
  policyLink: { fontSize: type.body.fontSize, marginBottom: spacing.lg },
  scroll: { flexGrow: 1, justifyContent: 'center' },
  signOut: { marginTop: spacing.lg },
  signOutText: { fontSize: type.body.fontSize, textAlign: 'center' },
  subtitle: { fontSize: type.body.fontSize, marginBottom: spacing.lg },
  title: { fontSize: type.display.fontSize, fontWeight: '700' },
});
