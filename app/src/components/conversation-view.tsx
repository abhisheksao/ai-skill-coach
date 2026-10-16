import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ChatBubble } from '@abhisheksao/ai-skill-coach-core/components/chat-bubble';
import { LoadingDots } from '@abhisheksao/ai-skill-coach-core/components/loading-dots';
import { ChatMessage } from '@/hooks/use-chat-session';
import { useVoiceSession } from '@abhisheksao/ai-skill-coach-core/use-voice-session';
import { Modality } from '@/lib/api';
import { getVoiceCapabilities, resolveMicDisabledReason, VoiceCapabilities } from '@abhisheksao/ai-skill-coach-core/voice-capabilities';
import { spacing, type, useTheme } from '@abhisheksao/ai-skill-coach-core/theme';

type Props = {
  messages: ChatMessage[];
  draft: string;
  onDraftChange: (text: string) => void;
  onSend: (overrideText?: string, modality?: Modality) => void;
  /** V4 (005): retries a single failed message by id, in place. */
  onRetry?: (messageId: string, content: string) => void;
  sending: boolean;
  errorKey: string | null;
  emptyStateKey?: string;
  suggestedReplies?: string[];
  /** Profile language code (e.g. 'en', 'hi') — drives the recognizer's
   * locale. Defaults to 'en' if the profile hasn't loaded yet. */
  voiceLanguage?: string;
  /** FR-004: user's persisted spoken-replies preference. Defaults to
   * true (matches the profile column's own default) if not yet loaded. */
  voiceRepliesEnabled?: boolean;
};

/** Shared bubble list + input row for both the wizard (onboarding) and
 * ongoing skill conversations — same UI, same modality (Constitution IV).
 * `behavior="height"` on Android: `undefined` (the RN default suggestion)
 * does nothing here and the keyboard covers the input; paired with
 * app.json's android.softwareKeyboardLayoutMode="resize". */
export function ConversationView({
  messages,
  draft,
  onDraftChange,
  onSend,
  onRetry,
  sending,
  errorKey,
  emptyStateKey = 'chat.emptyState',
  suggestedReplies = [],
  voiceLanguage = 'en',
  voiceRepliesEnabled = true,
}: Props) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const listRef = useRef<FlatList<ChatMessage>>(null);
  const pendingVoiceRef = useRef(false);
  const lastSpokenMessageIdRef = useRef<string | null>(null);
  const hasCapturedInitialMessageRef = useRef(false);
  // Optimistic default (enabled) until the async check resolves, same
  // spirit as `voiceRepliesEnabled`/`voiceLanguage` defaulting before the
  // profile loads -- avoids a disabled-then-enabled flash on every mount.
  const [capabilities, setCapabilities] = useState<VoiceCapabilities>({ stt: true, tts: true });

  const voice = useVoiceSession({ language: voiceLanguage });

  // Re-checked whenever the language changes (cheap, cached inside
  // getVoiceCapabilities per call).
  useEffect(() => {
    let cancelled = false;
    getVoiceCapabilities(voiceLanguage).then((caps) => {
      if (!cancelled) setCapabilities(caps);
    });
    return () => {
      cancelled = true;
    };
  }, [voiceLanguage]);

  // US2: speak a new assistant reply aloud when the user hasn't disabled
  // spoken replies and TTS is available for this language (clarified
  // FR-007 -- TTS-unavailable never blocks voice input, it just means no
  // auto-speak, same as the preference being off). On a *resumed*
  // conversation, `messages` arrives pre-populated from history -- the
  // first population must only record a baseline, never speak, or every
  // reopened chat re-speaks whatever reply happened to be last (a real
  // bug found via live testing: two speak calls instead of one).
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last) return;
    if (!hasCapturedInitialMessageRef.current) {
      hasCapturedInitialMessageRef.current = true;
      lastSpokenMessageIdRef.current = last.id;
      return;
    }
    if (last.sender !== 'assistant') return;
    if (last.id === lastSpokenMessageIdRef.current) return;
    lastSpokenMessageIdRef.current = last.id;
    if (voiceRepliesEnabled && capabilities.tts) {
      voice.speak(last.content);
    }
  }, [messages, voiceRepliesEnabled, capabilities.tts, voice]);

  // US3: mic button disables with guidance when STT is unsupported for
  // this device/language, or when the user has denied the permission
  // prompt (FR-006/FR-007). "unavailable" takes priority over "denied".
  const micDisabledReason = resolveMicDisabledReason({
    sttAvailable: capabilities.stt,
    permissionDenied: voice.permissionDenied,
  });

  // Once recognition finalizes, hand the transcript to the existing
  // draft/TextInput/Send machinery instead of duplicating it (US1) --
  // editing the transcript here still counts as voice-originated (FR-005:
  // "the stored text is the user-confirmed transcript, not the raw
  // recognizer output").
  useEffect(() => {
    if (voice.status === 'editable-final') {
      pendingVoiceRef.current = true;
      onDraftChange(voice.finalTranscript);
    }
  }, [voice.status, voice.finalTranscript, onDraftChange]);

  const handleDraftChange = useCallback(
    (text: string) => {
      if (text.length === 0) {
        // Cleared entirely -- treat whatever's typed next as a fresh chat
        // message rather than a further edit of the discarded transcript.
        pendingVoiceRef.current = false;
      }
      onDraftChange(text);
    },
    [onDraftChange]
  );

  const handleSend = useCallback(
    (overrideText?: string) => {
      const modality: Modality = pendingVoiceRef.current ? 'voice' : 'chat';
      pendingVoiceRef.current = false;
      voice.reset();
      onSend(overrideText, modality);
    },
    [onSend, voice]
  );

  const showVoiceStatusRow = voice.status !== 'idle';

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.flex}
      keyboardVerticalOffset={spacing.lg}
    >
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <ChatBubble
            sender={item.sender}
            content={item.content}
            status={item.status}
            onRetry={() => onRetry?.(item.id, item.content)}
          />
        )}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <Text style={[styles.empty, { color: colors.textMuted }]}>{t(emptyStateKey)}</Text>
        }
      />

      {sending ? <LoadingDots /> : null}
      {errorKey ? <Text style={[styles.error, { color: colors.error }]}>{t(errorKey)}</Text> : null}

      {showVoiceStatusRow ? (
        <View style={styles.voiceStatusRow}>
          {voice.status === 'recording' ? (
            voice.interimMode === 'interim-text' ? (
              <Text style={[styles.voiceStatusText, { color: colors.text }]}>
                {voice.interimText || t('voice.listening')}
              </Text>
            ) : (
              <Text style={[styles.voiceStatusText, { color: colors.textMuted }]}>
                {t('voice.listening')}
              </Text>
            )
          ) : null}
          {voice.status === 'editable-final' && voice.needsConfirmation ? (
            <Text style={[styles.voiceHint, { color: colors.textMuted }]}>
              {t('voice.lowConfidenceHint')}
            </Text>
          ) : null}
        </View>
      ) : null}

      {voice.interruption ? (
        <Text style={[styles.voiceHint, { color: colors.textMuted }]}>
          {voice.interruption === 'network'
            ? t('voice.connectionLost')
            : t('voice.audioFocusLost')}
        </Text>
      ) : null}

      {voice.ttsFailed ? (
        <Text style={[styles.voiceHint, { color: colors.textMuted }]}>
          {t('voice.ttsUnavailableBanner')}
        </Text>
      ) : null}

      {micDisabledReason ? (
        <Text style={[styles.voiceHint, { color: colors.textMuted }]}>
          {micDisabledReason === 'denied'
            ? t('voice.permissionDeniedGuidance')
            : t('voice.unavailableGuidance')}
        </Text>
      ) : null}

      {suggestedReplies.length > 0 && !sending && !showVoiceStatusRow ? (
        <View style={styles.suggestionRow}>
          {suggestedReplies.map((option) => (
            <Pressable
              key={option}
              accessibilityRole="button"
              onPress={() => handleSend(option)}
              style={[
                styles.suggestionChip,
                { backgroundColor: colors.surface, borderColor: colors.primary },
              ]}
            >
              <Text style={{ color: colors.primary, fontSize: type.body.fontSize }}>{option}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={styles.inputRow}>
        <TextInput
          value={draft}
          onChangeText={handleDraftChange}
          placeholder={t('chat.placeholder')}
          placeholderTextColor={colors.textMuted}
          multiline
          style={[
            styles.input,
            { backgroundColor: colors.surface, borderColor: colors.border, color: colors.text },
          ]}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('voice.holdToSpeak')}
          accessibilityState={{ disabled: sending || micDisabledReason !== null }}
          onPressIn={micDisabledReason ? undefined : voice.start}
          onPressOut={micDisabledReason ? undefined : voice.stop}
          disabled={sending || micDisabledReason !== null}
          style={({ pressed }) => [
            styles.micButton,
            {
              backgroundColor:
                voice.status === 'recording'
                  ? colors.error
                  : pressed
                    ? colors.primaryPressed
                    : colors.surface,
              borderColor: colors.primary,
              opacity: sending || micDisabledReason !== null ? 0.5 : 1,
            },
          ]}
        >
          <Text
            style={[
              styles.micLabel,
              { color: voice.status === 'recording' ? colors.textOnPrimary : colors.primary },
            ]}
          >
            {t('voice.micButtonLabel')}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={() => handleSend()}
          disabled={!draft.trim() || sending}
          style={({ pressed }) => [
            styles.sendButton,
            {
              backgroundColor: pressed ? colors.primaryPressed : colors.primary,
              opacity: !draft.trim() || sending ? 0.5 : 1,
            },
          ]}
        >
          <Text style={[styles.sendLabel, { color: colors.textOnPrimary }]}>{t('chat.send')}</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  empty: { marginTop: spacing.xl, textAlign: 'center' },
  error: { marginBottom: spacing.sm, textAlign: 'center' },
  flex: { flex: 1 },
  input: {
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    fontSize: type.body.fontSize,
    maxHeight: 120,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  inputRow: { alignItems: 'flex-end', flexDirection: 'row', gap: spacing.sm },
  list: { flexGrow: 1, paddingVertical: spacing.sm },
  micButton: {
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1.5,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  micLabel: { ...type.body, fontWeight: '600' },
  sendButton: {
    alignItems: 'center',
    borderRadius: 12,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  sendLabel: { ...type.body, fontWeight: '600' },
  suggestionChip: {
    borderRadius: 20,
    borderWidth: 1.5,
    marginBottom: spacing.sm,
    marginRight: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  suggestionRow: { flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.sm },
  voiceHint: { fontSize: type.caption.fontSize, marginTop: spacing.xs },
  voiceStatusRow: { marginBottom: spacing.sm },
  voiceStatusText: { fontSize: type.body.fontSize, fontStyle: 'italic' },
});
