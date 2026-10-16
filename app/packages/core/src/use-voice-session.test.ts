import React from 'react';
import TestRenderer, { act } from 'react-test-renderer';

import { resolveInterimMode, shouldPromptConfirmation, useVoiceSession } from './use-voice-session';

import { ExpoSpeechRecognitionModule } from 'expo-speech-recognition';
import * as Speech from 'expo-speech';
import { PermissionStatus } from 'expo-modules-core';

const eventListeners: Record<string, (event: any) => void> = {};

jest.mock('expo-speech-recognition', () => ({
  ExpoSpeechRecognitionModule: {
    start: jest.fn(),
    stop: jest.fn(),
    abort: jest.fn(),
    isRecognitionAvailable: jest.fn(),
    getSupportedLocales: jest.fn(),
    requestPermissionsAsync: jest.fn(),
    getPermissionsAsync: jest.fn(),
  },
  // Captures the latest listener per event name (the hook re-registers
  // fresh closures every render) so tests can fire a real event by hand.
  useSpeechRecognitionEvent: jest.fn((eventName: string, listener: (event: any) => void) => {
    eventListeners[eventName] = listener;
  }),
}));

function triggerRecognitionEvent(eventName: string, payload: unknown): void {
  act(() => {
    eventListeners[eventName]?.(payload);
  });
}

jest.mock('expo-speech', () => ({
  speak: jest.fn(),
  stop: jest.fn(),
  getAvailableVoicesAsync: jest.fn(),
}));

const mockedRecognition = ExpoSpeechRecognitionModule as jest.Mocked<
  typeof ExpoSpeechRecognitionModule
>;
const mockedSpeech = Speech as jest.Mocked<typeof Speech>;

/** No @testing-library/react(-native) in this project (see tasks.md's
 * header note) -- react-test-renderer (already a transitive RN dep) plus
 * a throwaway host component is the standard manual way to render a hook
 * and read its live return value across re-renders. */
const renderers: TestRenderer.ReactTestRenderer[] = [];

function renderVoiceSession(language = 'en') {
  let latest: ReturnType<typeof useVoiceSession>;
  function Host() {
    latest = useVoiceSession({ language });
    return null;
  }
  let renderer: TestRenderer.ReactTestRenderer;
  act(() => {
    renderer = TestRenderer.create(React.createElement(Host));
  });
  renderers.push(renderer!);
  return {
    current: () => latest,
  };
}

afterEach(() => {
  // Unmount every renderer so the grace-window setTimeout inside
  // use-voice-session.ts's start() doesn't leak past the test.
  act(() => {
    for (const renderer of renderers.splice(0)) renderer.unmount();
  });
});

beforeEach(() => {
  // Default every test to "permission already granted" so tests written
  // before US3 (permission handling) don't need to know about it; the
  // dedicated permission describe block below overrides this per-test.
  mockedRecognition.getPermissionsAsync.mockResolvedValue({
    status: PermissionStatus.GRANTED,
    granted: true,
    canAskAgain: true,
    expires: 'never',
  });
});

describe('shouldPromptConfirmation', () => {
  it('fires when the platform reports confidence below 0.5 (FR-003)', () => {
    expect(shouldPromptConfirmation(0.49)).toBe(true);
    expect(shouldPromptConfirmation(0)).toBe(true);
  });

  it('does not fire at or above the 0.5 threshold', () => {
    expect(shouldPromptConfirmation(0.5)).toBe(false);
    expect(shouldPromptConfirmation(1)).toBe(false);
  });

  it('never fires when no confidence score was reported (undefined) — clarified FR-003', () => {
    expect(shouldPromptConfirmation(undefined)).toBe(false);
  });
});

describe('resolveInterimMode', () => {
  it('renders live interim text when the recognizer streams partial results', () => {
    expect(resolveInterimMode(true)).toBe('interim-text');
  });

  it('degrades to a "Listening…" indicator on batch-only recognizers — clarified FR-002', () => {
    expect(resolveInterimMode(false)).toBe('listening-indicator');
  });
});

describe('useVoiceSession — speak/stopSpeaking and interrupt-on-start (US2)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('start() unconditionally calls Speech.stop() before starting recognition (US2 scenario 2)', async () => {
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });

    expect(mockedSpeech.stop).toHaveBeenCalledTimes(1);
    expect(mockedRecognition.start).toHaveBeenCalledTimes(1);
    const stopOrder = mockedSpeech.stop.mock.invocationCallOrder[0];
    const startOrder = mockedRecognition.start.mock.invocationCallOrder[0];
    expect(stopOrder).toBeLessThan(startOrder);
  });

  it('speak() calls Speech.speak with the given text', () => {
    const session = renderVoiceSession();

    act(() => {
      session.current().speak('Nice work today!');
    });

    expect(mockedSpeech.speak).toHaveBeenCalledWith('Nice work today!', expect.any(Object));
  });

  it('stopSpeaking() calls Speech.stop() (idempotent no-op if nothing is speaking)', () => {
    const session = renderVoiceSession();

    act(() => {
      session.current().stopSpeaking();
    });

    expect(mockedSpeech.stop).toHaveBeenCalledTimes(1);
  });
});

describe('useVoiceSession — contextual permission request (US3, FR-006)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows the OS permission prompt on first use when status is undetermined, then proceeds to start recording', async () => {
    mockedRecognition.getPermissionsAsync.mockResolvedValue({
      status: PermissionStatus.UNDETERMINED,
      granted: false,
      canAskAgain: true,
      expires: 'never',
    });
    mockedRecognition.requestPermissionsAsync.mockResolvedValue({
      status: PermissionStatus.GRANTED,
      granted: true,
      canAskAgain: true,
      expires: 'never',
    });
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });

    expect(mockedRecognition.requestPermissionsAsync).toHaveBeenCalledTimes(1);
    expect(mockedRecognition.start).toHaveBeenCalledTimes(1);
    expect(session.current().permissionDenied).toBe(false);
  });

  it('never calls ExpoSpeechRecognitionModule.start() when permission is denied, and never re-prompts once already granted/denied is known', async () => {
    mockedRecognition.getPermissionsAsync.mockResolvedValue({
      status: PermissionStatus.DENIED,
      granted: false,
      canAskAgain: false,
      expires: 'never',
    });
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });

    expect(mockedRecognition.requestPermissionsAsync).not.toHaveBeenCalled();
    expect(mockedRecognition.start).not.toHaveBeenCalled();
    expect(session.current().permissionDenied).toBe(true);
  });

  it('re-checks status (without re-prompting) on every subsequent start(), so a mid-session OS Settings grant is picked up', async () => {
    mockedRecognition.getPermissionsAsync
      .mockResolvedValueOnce({
        status: PermissionStatus.DENIED,
        granted: false,
        canAskAgain: false,
        expires: 'never',
      })
      .mockResolvedValueOnce({ status: PermissionStatus.GRANTED, granted: true, canAskAgain: true, expires: 'never' });
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });
    expect(session.current().permissionDenied).toBe(true);

    await act(async () => {
      await session.current().start();
    });
    expect(session.current().permissionDenied).toBe(false);
    expect(mockedRecognition.start).toHaveBeenCalledTimes(1);
  });

  it('sets permissionDenied on a "not-allowed" error event -- web\'s getPermissionsAsync/requestPermissionsAsync are no-ops there (always report granted), so this is the only signal on that platform', async () => {
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });
    expect(session.current().permissionDenied).toBe(false);

    triggerRecognitionEvent('error', { error: 'not-allowed', message: 'Permission denied' });

    expect(session.current().permissionDenied).toBe(true);
  });

  it('does not set permissionDenied on unrelated error codes (e.g. "no-speech")', async () => {
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });

    triggerRecognitionEvent('error', { error: 'no-speech', message: 'No speech detected' });

    expect(session.current().permissionDenied).toBe(false);
  });
});

/** 005 US3, research.md R9's remaining matrix cells. The text composer's
 * "never disabled" invariant is structural, not tested here: conversation-
 * view.tsx's TextInput never binds an `editable`/`disabled` prop to any
 * hook state at all -- there is no code path in that component capable of
 * disabling it, regardless of what these hook states report. */
describe('useVoiceSession — mid-session failure states (005 US3, research.md R9)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedRecognition.getPermissionsAsync.mockResolvedValue({
      status: PermissionStatus.GRANTED,
      granted: true,
      canAskAgain: true,
      expires: 'never',
    });
  });

  it('V2: permission revoked mid-session (granted, then denied) is caught on the next press -- same guidance state as V1, never a crash', async () => {
    mockedRecognition.getPermissionsAsync
      .mockResolvedValueOnce({
        status: PermissionStatus.GRANTED,
        granted: true,
        canAskAgain: true,
        expires: 'never',
      })
      .mockResolvedValueOnce({
        status: PermissionStatus.DENIED,
        granted: false,
        canAskAgain: false,
        expires: 'never',
      });
    const session = renderVoiceSession();

    await act(async () => {
      await session.current().start();
    });
    expect(session.current().permissionDenied).toBe(false);
    session.current().stop();
    triggerRecognitionEvent('end', {});

    await act(async () => {
      await session.current().start();
    });

    expect(session.current().permissionDenied).toBe(true);
    expect(mockedRecognition.start).toHaveBeenCalledTimes(1); // 2nd start() never actually recorded
  });

  it('V5: a "network" error mid-recognition preserves the interim transcript into the editable composer with a distinct interruption reason', async () => {
    const session = renderVoiceSession();
    await act(async () => {
      await session.current().start();
    });

    triggerRecognitionEvent('result', {
      isFinal: false,
      results: [{ transcript: 'swimming three times a', confidence: 0 }],
    });
    expect(session.current().interimText).toBe('swimming three times a');

    triggerRecognitionEvent('error', { error: 'network', message: 'network lost' });

    expect(session.current().status).toBe('editable-final');
    expect(session.current().finalTranscript).toBe('swimming three times a');
    expect(session.current().interruption).toBe('network');
  });

  it('V7: an "aborted" error (audio focus lost) preserves the partial transcript with a reason distinct from V5', async () => {
    const session = renderVoiceSession();
    await act(async () => {
      await session.current().start();
    });

    triggerRecognitionEvent('result', {
      isFinal: false,
      results: [{ transcript: 'kick drills every', confidence: 0 }],
    });

    triggerRecognitionEvent('error', { error: 'aborted', message: 'interrupted' });

    expect(session.current().status).toBe('editable-final');
    expect(session.current().finalTranscript).toBe('kick drills every');
    expect(session.current().interruption).toBe('audio-focus');
  });

  it('V5/V7 with no interim transcript captured yet stop cleanly to idle rather than an empty editable-final bubble', async () => {
    const session = renderVoiceSession();
    await act(async () => {
      await session.current().start();
    });

    triggerRecognitionEvent('error', { error: 'network', message: 'network lost' });

    expect(session.current().status).toBe('idle');
    expect(session.current().interruption).toBe('network');
  });

  it('a fresh start() clears any previous interruption reason', async () => {
    const session = renderVoiceSession();
    await act(async () => {
      await session.current().start();
    });
    triggerRecognitionEvent('error', { error: 'network', message: 'x' });
    expect(session.current().interruption).toBe('network');

    await act(async () => {
      await session.current().start();
    });
    expect(session.current().interruption).toBeNull();
  });
});
