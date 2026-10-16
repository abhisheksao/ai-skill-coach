import * as Localization from 'expo-localization';
import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { LanguagePicker } from '@/components/language-picker';
import { PrimaryButton } from '@abhisheksao/ai-skill-coach-core/components/primary-button';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { TextField } from '@abhisheksao/ai-skill-coach-core/components/text-field';
import { SupportedLanguage } from '@/i18n';
import { ApiError, postProfile } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { Profile, supabase } from '@/lib/supabase';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

// 005, contracts/api.md's client-facing config note: URL swap only, no
// build logic change -- placeholder policy page now, static page later.
const DELETE_ACCOUNT_URL =
  process.env.EXPO_PUBLIC_DELETE_ACCOUNT_URL ?? 'https://example.com/skillcoach-delete-account';

/** FR-011: language and display name remain changeable after the initial
 *  profile step, which becomes unreachable once a profile exists.
 *
 *  Real bug found via live testing: `profile` frequently arrives async
 *  after mount (e.g. right after a page reload, before the auth context
 *  has re-fetched it) -- useState initializers only ever read it once, so
 *  a late-arriving profile silently never reached the form. Pre-existing
 *  for language/displayName too (only voiceRepliesEnabled is new to this
 *  feature). Fixed by keying SettingsForm on the profile's identity so it
 *  fully remounts (re-running the initializers) once profile loads,
 *  rather than syncing via a setState-in-effect (React's own guidance
 *  against that pattern -- this project's lint enforces it). */
export default function Settings() {
  const { profile } = useAuth();
  return <SettingsForm key={profile?.user_id ?? 'loading'} profile={profile} />;
}

function SettingsForm({ profile }: { profile: Profile | null }) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const { session, refreshProfile } = useAuth();
  const router = useRouter();

  const [language, setLanguage] = useState<SupportedLanguage>(profile?.language ?? 'en');
  const [displayName, setDisplayName] = useState(profile?.display_name ?? '');
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = useState(
    profile?.voice_replies_enabled ?? true
  );
  const [saving, setSaving] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const dirty =
    language !== profile?.language ||
    displayName !== (profile?.display_name ?? '') ||
    voiceRepliesEnabled !== (profile?.voice_replies_enabled ?? true);

  async function handleSave() {
    setSaving(true);
    setErrorKey(null);
    setSaved(false);
    try {
      await postProfile({
        display_name: displayName.trim() || null,
        language,
        timezone: profile?.timezone ?? Localization.getCalendars()[0]?.timeZone ?? 'UTC',
        consent: true, // already consented at the profile step; editing isn't re-consenting
        voice_replies_enabled: voiceRepliesEnabled,
      });
      await refreshProfile(); // also applies the new language app-wide
      setSaved(true);
    } catch (error) {
      setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal');
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOut() {
    setSigningOut(true);
    await supabase.auth.signOut();
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Pressable accessibilityRole="button" onPress={() => router.back()}>
            <Text style={[styles.back, { color: colors.primary }]}>‹</Text>
          </Pressable>
          <Text style={[styles.title, { color: colors.text }]}>{t('settings.title')}</Text>
        </View>

        <Text style={[styles.email, { color: colors.textMuted }]}>{session?.user.email}</Text>

        <Text style={[styles.label, { color: colors.textMuted }]}>{t('profile.language')}</Text>
        <LanguagePicker value={language} onChange={setLanguage} />

        <TextField
          label={t('profile.displayName')}
          value={displayName}
          onChangeText={setDisplayName}
          maxLength={60}
        />

        <Pressable
          accessibilityRole="switch"
          accessibilityState={{ checked: voiceRepliesEnabled }}
          onPress={() => setVoiceRepliesEnabled((enabled) => !enabled)}
          style={styles.voiceToggleRow}
        >
          <View
            style={[
              styles.voiceToggleBox,
              {
                backgroundColor: voiceRepliesEnabled ? colors.primary : colors.surface,
                borderColor: voiceRepliesEnabled ? colors.primary : colors.border,
              },
            ]}
          >
            {voiceRepliesEnabled ? (
              <Text style={{ color: colors.textOnPrimary, fontWeight: '700' }}>✓</Text>
            ) : null}
          </View>
          <Text style={[styles.voiceToggleText, { color: colors.text }]}>
            {t('voice.spokenReplies')}
          </Text>
        </Pressable>

        {errorKey ? (
          <Text style={[styles.error, { color: colors.error }]}>{t(errorKey)}</Text>
        ) : null}
        {saved && !dirty ? (
          <Text style={[styles.saved, { color: colors.success }]}>{t('settings.saved')}</Text>
        ) : null}

        <PrimaryButton
          label={t('common.save')}
          onPress={handleSave}
          disabled={!dirty}
          loading={saving}
        />

        <View style={styles.signOutRow}>
          <PrimaryButton label={t('auth.signOut')} onPress={handleSignOut} loading={signingOut} />
        </View>

        <Pressable
          accessibilityRole="link"
          onPress={() => WebBrowser.openBrowserAsync(DELETE_ACCOUNT_URL)}
          style={styles.deleteAccountRow}
        >
          <Text style={[styles.deleteAccountText, { color: colors.error }]}>
            {t('settings.deleteAccount')}
          </Text>
        </Pressable>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: { fontSize: 32, fontWeight: '600', marginRight: spacing.md },
  deleteAccountRow: { alignItems: 'center', marginTop: spacing.lg },
  deleteAccountText: { fontSize: type.body.fontSize, textAlign: 'center' },
  email: { fontSize: type.body.fontSize, marginBottom: spacing.lg },
  error: { marginBottom: spacing.sm, textAlign: 'center' },
  header: { alignItems: 'center', flexDirection: 'row', marginBottom: spacing.lg },
  label: { fontSize: type.caption.fontSize, marginBottom: spacing.xs },
  saved: { marginBottom: spacing.sm, textAlign: 'center' },
  scroll: { flexGrow: 1 },
  signOutRow: { marginTop: spacing.xl },
  title: { ...type.title },
  voiceToggleBox: {
    alignItems: 'center',
    borderRadius: 6,
    borderWidth: 1.5,
    height: 24,
    justifyContent: 'center',
    marginRight: spacing.sm,
    width: 24,
  },
  voiceToggleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    marginBottom: spacing.lg,
    marginTop: spacing.sm,
  },
  voiceToggleText: { flex: 1, fontSize: type.body.fontSize },
});
