import { Link } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '@abhisheksao/ai-skill-coach-core/components/primary-button';
import { Screen } from '@abhisheksao/ai-skill-coach-core/components/screen';
import { TextField } from '@abhisheksao/ai-skill-coach-core/components/text-field';
import { signInWithApple, signInWithGoogle } from '@/lib/oauth';
import { supabase } from '@/lib/supabase';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

export default function SignIn() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const canSubmit = email.includes('@') && password.length >= 6;

  async function handleSignIn() {
    setLoading(true);
    setErrorText(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (error) {
      setErrorText(
        error.message.toLowerCase().includes('invalid')
          ? t('auth.errors.invalidCredentials')
          : t('auth.errors.generic')
      );
    }
    // Success: the auth gate in _layout routes onward.
  }

  async function handleGoogle() {
    setErrorText(null);
    try {
      await signInWithGoogle();
    } catch {
      setErrorText(t('auth.errors.generic'));
    }
  }

  async function handleApple() {
    setErrorText(null);
    try {
      await signInWithApple();
    } catch (error) {
      // A user-initiated cancel isn't an error worth surfacing.
      if ((error as { code?: string })?.code === 'ERR_REQUEST_CANCELED') return;
      setErrorText(t('auth.errors.generic'));
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <View style={styles.header}>
          <Text style={[styles.appName, { color: colors.primary }]}>{t('common.appName')}</Text>
          <Text style={[styles.title, { color: colors.text }]}>{t('auth.signIn')}</Text>
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

        <PrimaryButton
          label={t('auth.signIn')}
          onPress={handleSignIn}
          disabled={!canSubmit}
          loading={loading}
          testID="sign-in-submit"
        />

        <Text style={[styles.or, { color: colors.textMuted }]}>{t('common.or')}</Text>

        <Pressable
          accessibilityRole="button"
          onPress={handleGoogle}
          style={[styles.googleButton, { borderColor: colors.border, backgroundColor: colors.surface }]}
        >
          <Text style={[styles.googleLabel, { color: colors.text }]}>
            {t('auth.signInWithGoogle')}
          </Text>
        </Pressable>

        {Platform.OS === 'ios' ? (
          <Pressable
            accessibilityRole="button"
            onPress={handleApple}
            style={[styles.appleButton, { backgroundColor: colors.text }]}
          >
            <Text style={[styles.appleLabel, { color: colors.bg }]}>
              {t('auth.signInWithApple')}
            </Text>
          </Pressable>
        ) : null}

        <Link href="/sign-up" style={[styles.link, { color: colors.primary }]}>
          {t('auth.noAccount')}
        </Link>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  appName: { ...type.title, marginBottom: spacing.xs },
  appleButton: {
    alignItems: 'center',
    borderRadius: 12,
    justifyContent: 'center',
    marginTop: spacing.sm,
    minHeight: 48,
  },
  appleLabel: { ...type.body, fontWeight: '600' },
  flex: { flex: 1, justifyContent: 'center' },
  googleButton: {
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 48,
  },
  googleLabel: { ...type.body, fontWeight: '600' },
  header: { marginBottom: spacing.lg },
  link: { ...type.body, marginTop: spacing.lg, textAlign: 'center' },
  or: { marginVertical: spacing.md, textAlign: 'center' },
  title: { ...type.display },
});
