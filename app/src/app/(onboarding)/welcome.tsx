import { useRouter } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '@ai-skill-coach/core/components/primary-button';
import { Screen } from '@ai-skill-coach/core/components/screen';
import { requestPushPermissionAndRegister } from '@/hooks/use-push-notifications';
import { markWelcomeSeen } from '@/lib/onboarding';
import { spacing, type, useTheme } from '@ai-skill-coach/core/theme';

const CARD_COUNT = 2;

/** First-run explainer (005 US5, research.md R12): shown exactly once
 * after the profile step, before the dashboard -- routed here by
 * _layout.tsx's auth gate, which checks lib/onboarding.ts's AsyncStorage
 * flag. Notification permission is requested ONLY from this screen's own
 * "enable nudges" action, never automatically on sign-in (see
 * use-push-notifications.ts's registerForPushNotifications for the
 * corresponding fix -- it used to auto-prompt on every sign-in with no
 * explanation, a real R12 violation found while building this screen).
 * Skippable at any point; either path marks the flag so it never shows
 * again. */
export default function Welcome() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [enabling, setEnabling] = useState(false);

  async function finish() {
    await markWelcomeSeen();
    router.replace('/dashboard');
  }

  async function enableNudges() {
    setEnabling(true);
    await requestPushPermissionAndRegister();
    setEnabling(false);
    await finish();
  }

  const isLastCard = step === CARD_COUNT - 1;

  return (
    <Screen>
      <View style={styles.content}>
        {step === 0 ? (
          <>
            <Text style={[styles.title, { color: colors.text }]}>
              {t('onboarding.pushToTalkTitle')}
            </Text>
            <Text style={[styles.body, { color: colors.textMuted }]}>
              {t('onboarding.pushToTalkBody')}
            </Text>
          </>
        ) : (
          <>
            <Text style={[styles.title, { color: colors.text }]}>
              {t('onboarding.notificationsTitle')}
            </Text>
            <Text style={[styles.body, { color: colors.textMuted }]}>
              {t('onboarding.notificationsBody')}
            </Text>
          </>
        )}
      </View>

      <View style={styles.footer}>
        <Pressable accessibilityRole="button" onPress={finish}>
          <Text style={[styles.skip, { color: colors.textMuted }]}>{t('onboarding.skip')}</Text>
        </Pressable>

        {isLastCard ? (
          <PrimaryButton
            label={t('onboarding.enableNudges')}
            onPress={enableNudges}
            loading={enabling}
          />
        ) : (
          <PrimaryButton label={t('common.continue')} onPress={() => setStep((s) => s + 1)} />
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: { fontSize: type.body.fontSize, textAlign: 'center' },
  content: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  footer: { gap: spacing.md, paddingBottom: spacing.lg },
  skip: { fontSize: type.body.fontSize, textAlign: 'center' },
  title: {
    fontSize: type.title.fontSize,
    fontWeight: '700',
    marginBottom: spacing.md,
    textAlign: 'center',
  },
});
