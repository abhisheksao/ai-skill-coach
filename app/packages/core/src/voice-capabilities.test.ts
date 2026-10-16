import * as Speech from 'expo-speech';
import { ExpoSpeechRecognitionModule } from 'expo-speech-recognition';

import {
  getVoiceCapabilities,
  markTtsFailed,
  resetTtsFailureForTests,
  resolveMicDisabledReason,
  resolveSttAvailability,
} from './voice-capabilities';

jest.mock('expo-speech', () => ({
  getAvailableVoicesAsync: jest.fn(),
}));

jest.mock('expo-speech-recognition', () => ({
  ExpoSpeechRecognitionModule: {
    isRecognitionAvailable: jest.fn(),
    getSupportedLocales: jest.fn(),
  },
}));

const mockedSpeech = Speech as jest.Mocked<typeof Speech>;
const mockedRecognition = ExpoSpeechRecognitionModule as jest.Mocked<
  typeof ExpoSpeechRecognitionModule
>;

describe('getVoiceCapabilities', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('reports STT and TTS independently supported when both are available (FR-007)', async () => {
    mockedRecognition.isRecognitionAvailable.mockReturnValue(true);
    mockedRecognition.getSupportedLocales.mockResolvedValue({
      locales: ['en-US', 'hi-IN'],
      installedLocales: ['en-US'],
    });
    mockedSpeech.getAvailableVoicesAsync.mockResolvedValue([
      { identifier: 'v1', name: 'V1', quality: 'Default' as Speech.VoiceQuality, language: 'en-US' },
    ]);

    const result = await getVoiceCapabilities('en');

    expect(result).toEqual({ stt: true, tts: true });
  });

  it('degrades independently: STT unavailable for a language does not affect TTS (clarified FR-007)', async () => {
    mockedRecognition.isRecognitionAvailable.mockReturnValue(true);
    mockedRecognition.getSupportedLocales.mockResolvedValue({
      locales: ['en-US'], // no fr-FR
      installedLocales: ['en-US'],
    });
    mockedSpeech.getAvailableVoicesAsync.mockResolvedValue([
      { identifier: 'v1', name: 'V1', quality: 'Default' as Speech.VoiceQuality, language: 'fr-FR' },
    ]);

    const result = await getVoiceCapabilities('fr');

    expect(result).toEqual({ stt: false, tts: true });
  });

  it('degrades independently: TTS unavailable for a language does not affect STT (clarified FR-007)', async () => {
    mockedRecognition.isRecognitionAvailable.mockReturnValue(true);
    mockedRecognition.getSupportedLocales.mockResolvedValue({
      locales: ['de-DE'],
      installedLocales: [],
    });
    mockedSpeech.getAvailableVoicesAsync.mockResolvedValue([
      { identifier: 'v1', name: 'V1', quality: 'Default' as Speech.VoiceQuality, language: 'en-US' }, // no de-DE
    ]);

    const result = await getVoiceCapabilities('de');

    expect(result).toEqual({ stt: true, tts: false });
  });

  it('reports STT unavailable when the recognizer itself is unavailable, regardless of locale', async () => {
    mockedRecognition.isRecognitionAvailable.mockReturnValue(false);
    mockedSpeech.getAvailableVoicesAsync.mockResolvedValue([]);

    const result = await getVoiceCapabilities('es');

    expect(result.stt).toBe(false);
    expect(mockedRecognition.getSupportedLocales).not.toHaveBeenCalled();
  });

  it('treats a getSupportedLocales rejection as STT-unavailable rather than throwing', async () => {
    mockedRecognition.isRecognitionAvailable.mockReturnValue(true);
    mockedRecognition.getSupportedLocales.mockRejectedValue(new Error('package_not_found'));
    mockedSpeech.getAvailableVoicesAsync.mockResolvedValue([]);

    const result = await getVoiceCapabilities('en');

    expect(result.stt).toBe(false);
  });
});

describe('markTtsFailed (005, research.md R9 -- V6)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    resetTtsFailureForTests();
  });

  afterEach(() => {
    resetTtsFailureForTests();
  });

  it('a runtime TTS failure makes getVoiceCapabilities report tts:false from then on, without re-probing', async () => {
    mockedRecognition.isRecognitionAvailable.mockReturnValue(true);
    mockedRecognition.getSupportedLocales.mockResolvedValue({
      locales: ['en-US'],
      installedLocales: ['en-US'],
    });
    mockedSpeech.getAvailableVoicesAsync.mockResolvedValue([
      { identifier: 'v1', name: 'V1', quality: 'Default' as Speech.VoiceQuality, language: 'en-US' },
    ]);

    expect((await getVoiceCapabilities('en')).tts).toBe(true);

    markTtsFailed();

    const result = await getVoiceCapabilities('en');
    expect(result.tts).toBe(false);
    expect(result.stt).toBe(true); // STT is unaffected -- independent degradation (FR-007)
    expect(mockedSpeech.getAvailableVoicesAsync).toHaveBeenCalledTimes(1); // not called again
  });
});

describe('resolveMicDisabledReason', () => {
  it('is enabled (null) when STT is available and permission has not been denied', () => {
    expect(resolveMicDisabledReason({ sttAvailable: true, permissionDenied: false })).toBeNull();
  });

  it('reports "unavailable" when STT is unsupported for the language/device, taking priority over permission state (US3, FR-007)', () => {
    expect(resolveMicDisabledReason({ sttAvailable: false, permissionDenied: false })).toBe(
      'unavailable'
    );
    expect(resolveMicDisabledReason({ sttAvailable: false, permissionDenied: true })).toBe(
      'unavailable'
    );
  });

  it('reports "denied" when STT is available but the user declined the permission prompt (US3 scenario 2)', () => {
    expect(resolveMicDisabledReason({ sttAvailable: true, permissionDenied: true })).toBe(
      'denied'
    );
  });
});

describe('resolveSttAvailability', () => {
  it('is false whenever the recognizer itself is unavailable, regardless of locale-list reliability', () => {
    expect(
      resolveSttAvailability({
        recognitionAvailable: false,
        localeListReliable: true,
        localeSupported: true,
      })
    ).toBe(false);
    expect(
      resolveSttAvailability({
        recognitionAvailable: false,
        localeListReliable: false,
        localeSupported: true,
      })
    ).toBe(false);
  });

  it('trusts isRecognitionAvailable alone when the locale list is unreliable -- real bug found live on two fronts: web (getSupportedLocales is a documented no-op there, always empty) AND Android API level <31 (documented in the package source: "Not supported on Android 12 and below... this will return an empty array"), confirmed on a real OnePlus 3 running Android 9 (API 28) reporting the mic permanently "unavailable" for en-US despite the recognizer genuinely working', () => {
    expect(
      resolveSttAvailability({
        recognitionAvailable: true,
        localeListReliable: false,
        localeSupported: false,
      })
    ).toBe(true);
  });

  it('requires the specific locale to actually be supported when the locale list is reliable (native, API 31+)', () => {
    expect(
      resolveSttAvailability({
        recognitionAvailable: true,
        localeListReliable: true,
        localeSupported: false,
      })
    ).toBe(false);
    expect(
      resolveSttAvailability({
        recognitionAvailable: true,
        localeListReliable: true,
        localeSupported: true,
      })
    ).toBe(true);
  });
});
