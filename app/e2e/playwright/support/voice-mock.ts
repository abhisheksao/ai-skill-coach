import type { Locator, Page } from '@playwright/test';

/**
 * React Native Web's Pressable listens for real pointer events on the
 * underlying DOM node -- a bare `locator.dispatchEvent('pointerdown')`
 * (a generic Event, not a full PointerEvent with button/pointerId/
 * isPrimary set) does not reliably trigger `onPressIn` (confirmed via a
 * live run: the exact same interaction worked for the *first* press in
 * one test but silently no-op'd for a second press moments later).
 * Playwright's real mouse simulation is what a genuine user interaction
 * uses under the hood, so route through it instead of raw dispatchEvent.
 */
export async function pressMicDown(locator: Locator): Promise<void> {
  const box = await locator.boundingBox();
  if (!box) throw new Error('mic button has no bounding box (not visible?)');
  const page = locator.page();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
}

export async function releaseMic(page: Page): Promise<void> {
  await page.mouse.up();
}

/**
 * Installs a fake `webkitSpeechRecognition` global before any page script
 * runs, so expo-speech-recognition's web polyfill (ExpoSpeechRecognitionModule.web.ts)
 * picks it up exactly as it would a real browser recognizer. Real STT
 * accuracy is out of scope for this suite (SC-004/FR-002 are about the
 * app's *reaction* to recognizer events, not recognition quality) --
 * `window.__voiceMock` lets a test script drive deterministic interim/
 * final results instead.
 *
 * Must be called before `page.goto()` (addInitScript runs on every
 * subsequent navigation/reload in this page, before the app's own JS).
 */
export async function installFakeSpeechRecognition(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const win = window as unknown as Record<string, any>;

    function FakeSpeechRecognition(this: any) {
      this.lang = 'en-US';
      this.interimResults = false;
      this.maxAlternatives = 1;
      this.continuous = false;
      this._listeners = {};
    }
    FakeSpeechRecognition.prototype.addEventListener = function (
      type: string,
      listener: (event: unknown) => void
    ) {
      (this._listeners[type] ??= []).push(listener);
    };
    FakeSpeechRecognition.prototype.removeEventListener = function (
      type: string,
      listener: (event: unknown) => void
    ) {
      this._listeners[type] = (this._listeners[type] ?? []).filter(
        (l: unknown) => l !== listener
      );
    };
    FakeSpeechRecognition.prototype._dispatch = function (type: string, event: unknown) {
      for (const listener of this._listeners[type] ?? []) listener(event);
    };
    FakeSpeechRecognition.prototype.start = function () {
      win.__activeRecognition = this;
      this._dispatch('start', {});
      this._dispatch('audiostart', {});
    };
    FakeSpeechRecognition.prototype.stop = function () {
      this._dispatch('end', {});
    };
    FakeSpeechRecognition.prototype.abort = function () {
      this._dispatch('end', {});
    };

    win.webkitSpeechRecognition = FakeSpeechRecognition;

    function emit(transcript: string, confidence: number, isFinal: boolean) {
      const rec = win.__activeRecognition;
      if (!rec) return;
      const alternative = { transcript, confidence };
      const result: unknown[] & { isFinal?: boolean } = [alternative];
      result.isFinal = isFinal;
      rec._dispatch('result', { results: [result], resultIndex: 0 });
    }

    win.__voiceMock = {
      emitInterim: (transcript: string) => emit(transcript, 0, false),
      emitFinal: (transcript: string, confidence: number) => emit(transcript, confidence, true),
      emitError: (errorCode: string) => {
        const rec = win.__activeRecognition;
        if (!rec) return;
        rec._dispatch('error', { error: errorCode, message: errorCode });
      },
    };
  });
}

/**
 * `use-voice-session.ts`'s `start()` is async (it awaits a permission
 * check -- see T033 -- before calling `ExpoSpeechRecognitionModule.start()`,
 * which is what actually constructs the fake recognition instance and
 * sets `window.__activeRecognition`). A bare `pressMicDown` followed
 * immediately by `emitInterim`/`emitFinal`/`emitError` races that async
 * chain -- the emit call can fire before the instance exists and
 * silently no-op (confirmed live: the app degraded to "Listening…"
 * because the interim event was dropped, not because the app is slow).
 * Wait for the instance to actually exist first.
 */
async function waitForActiveRecognition(page: Page): Promise<void> {
  await page.waitForFunction(
    () => Boolean((window as unknown as { __activeRecognition?: unknown }).__activeRecognition),
    { timeout: 5_000 }
  );
}

export async function emitInterim(page: Page, transcript: string): Promise<void> {
  await waitForActiveRecognition(page);
  await page.evaluate(
    ([text]) => (window as unknown as { __voiceMock: { emitInterim: (t: string) => void } }).__voiceMock.emitInterim(text),
    [transcript]
  );
}

export async function emitFinal(page: Page, transcript: string, confidence: number): Promise<void> {
  await waitForActiveRecognition(page);
  await page.evaluate(
    ([text, conf]) =>
      (
        window as unknown as {
          __voiceMock: { emitFinal: (t: string, c: number) => void };
        }
      ).__voiceMock.emitFinal(text as string, conf as number),
    [transcript, confidence]
  );
}

/**
 * Simulates a browser with no Web Speech API at all (Chrome-on-iOS,
 * Firefox, Safari per research.md R4) by deleting `webkitSpeechRecognition`/
 * `SpeechRecognition` before any page script runs -- real desktop Chrome
 * (this suite's actual browser) has `webkitSpeechRecognition` natively,
 * so simply *not* calling installFakeSpeechRecognition isn't enough to
 * simulate this case.
 */
export async function installUnsupportedBrowser(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const win = window as unknown as Record<string, any>;
    delete win.webkitSpeechRecognition;
    delete win.SpeechRecognition;
  });
}

export async function emitError(page: Page, errorCode: string): Promise<void> {
  await waitForActiveRecognition(page);
  await page.evaluate(
    ([code]) => (window as unknown as { __voiceMock: { emitError: (c: string) => void } }).__voiceMock.emitError(code),
    [errorCode]
  );
}

/**
 * Spies on `window.speechSynthesis.speak`/`.cancel` (expo-speech's web
 * implementation calls these directly -- Speech.speak -> .speak(utterance),
 * Speech.stop -> .cancel()) so a test can assert auto-speak fired (or
 * didn't) and measure interrupt latency, without needing real audio
 * output (headless Chrome exposes the Web Speech Synthesis API surface
 * even though nothing audible plays).
 */
export async function installTtsSpy(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const synth = window.speechSynthesis;
    const win = window as unknown as Record<string, any>;
    win.__ttsSpy = { speakCalls: [] as string[], cancelCount: 0 };

    const originalSpeak = synth.speak.bind(synth);
    synth.speak = (utterance: SpeechSynthesisUtterance) => {
      win.__ttsSpy.speakCalls.push(utterance.text);
      originalSpeak(utterance);
    };

    const originalCancel = synth.cancel.bind(synth);
    synth.cancel = () => {
      win.__ttsSpy.cancelCount += 1;
      win.__ttsSpy.lastCancelAt = Date.now();
      originalCancel();
    };
  });
}

export async function getTtsSpeakCalls(page: Page): Promise<string[]> {
  return page.evaluate(
    () => (window as unknown as { __ttsSpy: { speakCalls: string[] } }).__ttsSpy.speakCalls
  );
}

export async function getTtsCancelCount(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as unknown as { __ttsSpy: { cancelCount: number } }).__ttsSpy.cancelCount
  );
}
