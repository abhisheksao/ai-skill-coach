import { Link, useRouter } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '@abhisheksao/ai-skill-coach-core/components/primary-button';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { TextField } from '@abhisheksao/ai-skill-coach-core/components/text-field';
import { supabase } from '@/lib/supabase';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

export default function SignUp() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [infoText, setInfoText] = useState<string | null>(null);

  const canSubmit = email.includes('@') && password.length >= 6;

  async function handleSignUp() {
    setLoading(true);
    setErrorText(null);
    setInfoText(null);
    const { data, error } = await supabase.auth.signUp({ email, password });
    setLoading(false);

    if (error) {
      if (error.message.toLowerCase().includes('already registered')) {
        // Edge case (spec): clear path to sign-in, no second account.
        setErrorText(t('auth.errors.accountExists'));
        setTimeout(() => router.replace('/sign-in'), 1500);
      } else {
        setErrorText(t('auth.errors.generic'));
      }
      return;
    }

    if (!data.session) {
      // Email confirmation enabled on the Supabase project.
      setInfoText(t('auth.checkEmail'));
    }
    // With a session: the auth gate routes to the profile step (US3).
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Text style={[styles.appName, { color: colors.primary }]}>{t('common.appName')}</Text>
          <Text style={[styles.title, { color: colors.text }]}>{t('auth.signUp')}</Text>
        </View>

        <TextField
          label={t('auth.email')}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
        <TextField
          label={t('auth.password')}
          autoCapitalize="none"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          errorText={errorText}
        />

        {infoText ? <Text style={[styles.info, { color: colors.success }]}>{infoText}</Text> : null}

        <PrimaryButton
          label={t('auth.signUp')}
          onPress={handleSignUp}
          disabled={!canSubmit}
          loading={loading}
        />

        <Link href="/sign-in" style={[styles.link, { color: colors.primary }]}>
          {t('auth.haveAccount')}
        </Link>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  appName: { ...type.title, marginBottom: spacing.xs },
  flex: { flex: 1, justifyContent: 'center' },
  header: { marginBottom: spacing.lg },
  info: { marginBottom: spacing.md, textAlign: 'center' },
  link: { ...type.body, marginTop: spacing.lg, textAlign: 'center' },
  title: { ...type.display },
});
