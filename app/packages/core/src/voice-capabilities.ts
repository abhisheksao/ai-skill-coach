import * as Device from 'expo-device';
import * as Speech from 'expo-speech';
import { ExpoSpeechRecognitionModule } from 'expo-speech-recognition';
import { Platform } from 'react-native';

export type VoiceCapabilities = { stt: boolean; tts: boolean };

/** BCP-47 tags used by the recognizer/voice APIs, keyed by this app's
 * 2-letter profile language codes (Constitution X launch set). */
const LOCALE_TAGS: Record<string, string> = {
  en: 'en-US',
  hi: 'hi-IN',
  es: 'es-ES',
  fr: 'fr-FR',
  de: 'de-DE',
};

function localeTagFor(language: string): string {
  return LOCALE_TAGS[language] ?? language;
}

/** `getSupportedLocales()` returns an unreliable (always-empty) list on
 * two fronts, both found via live testing rather than assumption: web
 * (documented no-op in the package source) and Android API level <31
 * ("Not supported on Android 12 and below", same source) -- confirmed
 * live on a real OnePlus 3 (Android 9 / API 28), which reported the mic
 * permanently "unavailable" for en-US despite the recognizer genuinely
 * working. `isRecognitionAvailable()` alone is the only signal available
 * wherever the locale list can't be trusted. */
const ANDROID_LOCALE_LIST_MIN_API_LEVEL = 31;

export function resolveSttAvailability(input: {
  recognitionAvailable: boolean;
  localeListReliable: boolean;
  localeSupported: boolean;
}): boolean {
  if (!input.recognitionAvailable) return false;
  if (!input.localeListReliable) return true;
  return input.localeSupported;
}

function isLocaleListReliable(): boolean {
  if (Platform.OS === 'web') return false;
  if (Platform.OS === 'android') {
    return (Device.platformApiLevel ?? 0) >= ANDROID_LOCALE_LIST_MIN_API_LEVEL;
  }
  return true;
}

async function checkSttAvailable(localeTag: string): Promise<boolean> {
  const recognitionAvailable = ExpoSpeechRecognitionModule.isRecognitionAvailable();
  if (!recognitionAvailable) return false;

  let localeSupported = false;
  try {
    const { locales } = await ExpoSpeechRecognitionModule.getSupportedLocales({});
    localeSupported = locales.some((locale) => locale.toLowerCase() === localeTag.toLowerCase());
  } catch {
    localeSupported = false;
  }

  return resolveSttAvailability({
    recognitionAvailable,
    localeListReliable: isLocaleListReliable(),
    localeSupported,
  });
}

// V6 (005, research.md R9): once a real Speech.speak() call fails at
// runtime (the recognizer/voice engine itself erroring, not just a
// missing-voice probe), treat TTS as unavailable for the rest of this
// process -- mutable, in-memory, deliberately not per-language (a real
// synthesis failure is far more likely a systemic engine problem than a
// one-language gap; erring toward "stays off" beats repeatedly retrying
// and failing silently on every reply).
let ttsFailedAtRuntime = false;

export function markTtsFailed(): void {
  ttsFailedAtRuntime = true;
}

/** Test-only -- there is no product path that un-fails TTS mid-session. */
export function resetTtsFailureForTests(): void {
  ttsFailedAtRuntime = false;
}

async function checkTtsAvailable(localeTag: string): Promise<boolean> {
  if (ttsFailedAtRuntime) return false;
  try {
    const voices = await Speech.getAvailableVoicesAsync();
    return voices.some((voice) => voice.language?.toLowerCase() === localeTag.toLowerCase());
  } catch {
    return false;
  }
}

/** FR-007 (clarified): STT and TTS availability are detected and
 * degrade independently — a missing voice for a language never disables
 * recognition, and a missing recognizer locale never disables playback. */
export async function getVoiceCapabilities(language: string): Promise<VoiceCapabilities> {
  const localeTag = localeTagFor(language);
  const [stt, tts] = await Promise.all([checkSttAvailable(localeTag), checkTtsAvailable(localeTag)]);
  return { stt, tts };
}

export type MicDisabledReason = 'unavailable' | 'denied' | null;

/** US3: combines static capability (checked once per language, before
 * any attempt) with permission state (only known after the user's first
 * mic tap, since FR-006 requires the OS prompt to be contextual) into a
 * single reason to disable the mic button, or `null` when it's usable.
 * "unavailable" takes priority — a device/language that can't recognize
 * speech at all is a stronger disqualifier than a still-changeable
 * permission decision. */
export function resolveMicDisabledReason(input: {
  sttAvailable: boolean;
  permissionDenied: boolean;
}): MicDisabledReason {
  if (!input.sttAvailable) return 'unavailable';
  if (input.permissionDenied) return 'denied';
  return null;
}
