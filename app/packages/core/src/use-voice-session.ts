import * as Speech from 'expo-speech';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';

import { markTtsFailed } from './voice-capabilities';

/** BCP-47 tags for the recognizer, keyed by this app's 2-letter profile
 * language codes (Constitution X launch set) — same map as
 * voice-capabilities.ts, kept local to avoid a cross-file coupling for
 * one small object. */
const LOCALE_TAGS: Record<string, string> = {
  en: 'en-US',
  hi: 'hi-IN',
  es: 'es-ES',
  fr: 'fr-FR',
  de: 'de-DE',
};

const CONFIDENCE_THRESHOLD = 0.5;
/** How long to wait after start() for a first interim `result` event
 * before concluding this recognizer session doesn't stream partials
 * (clarified FR-002 — degrade to a "Listening…" indicator instead). */
const INTERIM_GRACE_MS = 1500;

/** FR-003 (clarified): fires only when the platform actually reported a
 * confidence score; `undefined` (no score reported at all) never fires
 * it — edit-before-send is the sole correction path on those platforms. */
export function shouldPromptConfirmation(confidence: number | undefined): boolean {
  if (confidence === undefined) return false;
  return confidence < CONFIDENCE_THRESHOLD;
}

export type InterimMode = 'interim-text' | 'listening-indicator';

/** FR-002 (clarified): maps recognizer partial-result support to a UI
 * mode — live text when supported, a static indicator otherwise. */
export function resolveInterimMode(supportsInterim: boolean): InterimMode {
  return supportsInterim ? 'interim-text' : 'listening-indicator';
}

export type VoiceStatus = 'idle' | 'recording' | 'editable-final';

/** 005, research.md R9 -- V5/V7: a recognizer error mid-session that
 * isn't a permission denial. Both preserve whatever partial transcript
 * existed into the composer (same editable-final path as a normal
 * result) and need distinct, honest copy naming what happened -- never
 * a generic "voice error". */
export type VoiceInterruption = 'network' | 'audio-focus' | null;

type Options = {
  /** 2-letter profile language code (e.g. 'en', 'hi'). */
  language: string;
};

/** Core push-to-talk state machine (US1). TTS (speak/stop) is added in
 * 003's US2 phase, permission handling in US3 — both extend this same
 * hook rather than living in separate files, per plan.md. */
export function useVoiceSession({ language }: Options) {
  const [status, setStatus] = useState<VoiceStatus>('idle');
  const [interimText, setInterimText] = useState('');
  const [interimMode, setInterimMode] = useState<InterimMode>('interim-text');
  const [finalTranscript, setFinalTranscript] = useState('');
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [interruption, setInterruption] = useState<VoiceInterruption>(null);
  const [ttsFailed, setTtsFailed] = useState(false);

  const receivedInterimRef = useRef(false);
  const graceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearGraceTimer = useCallback(() => {
    if (graceTimerRef.current) {
      clearTimeout(graceTimerRef.current);
      graceTimerRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    // US2 scenario 2: pressing push-to-talk always interrupts any
    // in-progress spoken reply first, unconditionally -- no need to
    // track "is something currently speaking" state to decide whether to
    // call this; Speech.stop() is a no-op if nothing is speaking.
    Speech.stop();

    // US3/FR-006: getPermissionsAsync is a cheap status check (no OS UI),
    // called every time so a mid-session OS Settings change is picked up;
    // requestPermissionsAsync (the actual native dialog) only fires the
    // first time ever, when status is genuinely undetermined -- that's
    // what makes this "contextual" rather than prompting repeatedly.
    let permission = await ExpoSpeechRecognitionModule.getPermissionsAsync();
    if (permission.status === 'undetermined') {
      permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
    }
    setPermissionDenied(!permission.granted);
    if (!permission.granted) return;

    receivedInterimRef.current = false;
    setInterimText('');
    setFinalTranscript('');
    setNeedsConfirmation(false);
    setInterimMode('interim-text');
    setInterruption(null);
    setStatus('recording');

    ExpoSpeechRecognitionModule.start({
      lang: LOCALE_TAGS[language] ?? language,
      interimResults: true,
      continuous: false,
    });

    clearGraceTimer();
    graceTimerRef.current = setTimeout(() => {
      if (!receivedInterimRef.current) {
        setInterimMode(resolveInterimMode(false));
      }
    }, INTERIM_GRACE_MS);
  }, [language, clearGraceTimer]);

  const stop = useCallback(() => {
    ExpoSpeechRecognitionModule.stop();
  }, []);

  const abort = useCallback(() => {
    clearGraceTimer();
    ExpoSpeechRecognitionModule.abort();
    setStatus('idle');
  }, [clearGraceTimer]);

  /** Discards the editable-final transcript without sending (e.g. the
   * user closes the confirm prompt), returning to idle. */
  const reset = useCallback(() => {
    setInterimText('');
    setFinalTranscript('');
    setNeedsConfirmation(false);
    setInterruption(null);
    setStatus('idle');
  }, []);

  /** US2: speaks a coach reply aloud, in the profile language. V6
   * (research.md R9): a runtime synthesis failure never throws -- it
   * marks TTS unavailable (both live, for this render, and in
   * voice-capabilities.ts's module state for future capability checks)
   * so the UI can show a text-only banner instead of silently doing
   * nothing forever. */
  const speak = useCallback(
    (text: string) => {
      Speech.speak(text, {
        language: LOCALE_TAGS[language] ?? language,
        onError: () => {
          markTtsFailed();
          setTtsFailed(true);
        },
      });
    },
    [language]
  );

  /** US2 scenario 3 (disable spoken replies): stops any in-progress
   * playback; a no-op if nothing is speaking. Named distinctly from the
   * recognizer's `stop` above -- unrelated concerns, same hook. */
  const stopSpeaking = useCallback(() => {
    Speech.stop();
  }, []);

  useSpeechRecognitionEvent('result', (event) => {
    const result = event.results[0];
    if (!result) return;

    if (!event.isFinal) {
      receivedInterimRef.current = true;
      setInterimMode(resolveInterimMode(true));
      setInterimText(result.transcript);
      return;
    }

    clearGraceTimer();
    // -1 = "unavailable" per the package's own docs; 0 also occurs on
    // partial results but this branch only ever sees isFinal results.
    const confidence = result.confidence < 0 ? undefined : result.confidence;
    setFinalTranscript(result.transcript);
    setNeedsConfirmation(shouldPromptConfirmation(confidence));
    setStatus('editable-final');
  });

  useSpeechRecognitionEvent('end', () => {
    setStatus((prev) => (prev === 'recording' ? 'idle' : prev));
  });

  useSpeechRecognitionEvent('error', (event) => {
    clearGraceTimer();
    // Web: getPermissionsAsync/requestPermissionsAsync are no-ops on this
    // platform (the package always reports "granted" there, per its own
    // source) -- denial only ever surfaces here, via the recognizer's own
    // error event, after a start() attempt. Native gets this signal
    // earlier via the permission check in start() above; this is a
    // second, web-specific path to the same `permissionDenied` state.
    if (event.error === 'not-allowed') {
      setPermissionDenied(true);
      setStatus('idle');
      return;
    }

    // V5 (network lost mid-recognition) / V7 (audio focus lost -- a call,
    // another app grabbing the mic): neither is a permission problem.
    // Whatever partial transcript existed is preserved into the composer
    // via the same editable-final path a normal final result uses, rather
    // than silently discarded; the specific reason drives distinct copy
    // (research.md R9 -- never a generic "voice error").
    const reason: VoiceInterruption =
      event.error === 'network' ? 'network' : event.error === 'aborted' ? 'audio-focus' : null;
    if (reason) {
      setInterruption(reason);
      if (interimText) {
        setFinalTranscript(interimText);
        setNeedsConfirmation(false);
        setStatus('editable-final');
        return;
      }
    }
    setStatus('idle');
  });

  useEffect(() => clearGraceTimer, [clearGraceTimer]);

  return {
    status,
    interimText,
    interimMode,
    finalTranscript,
    setFinalTranscript,
    needsConfirmation,
    permissionDenied,
    interruption,
    ttsFailed,
    start,
    stop,
    abort,
    reset,
    speak,
    stopSpeaking,
  };
}
