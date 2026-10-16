import React from 'react';
import TestRenderer, { act } from 'react-test-renderer';

import NetInfo from '@react-native-community/netinfo';

import { useChatSession } from '@/hooks/use-chat-session';
import { ApiError, postChat } from '@/lib/api';

jest.mock('@/lib/api', () => {
  class ApiError extends Error {
    code: string;
    messageKey: string;
    constructor(code: string, messageKey: string) {
      super(code);
      this.code = code;
      this.messageKey = messageKey;
    }
  }
  return { ApiError, postChat: jest.fn() };
});

jest.mock('@react-native-community/netinfo', () => ({
  __esModule: true,
  default: { addEventListener: jest.fn(() => jest.fn()) },
}));

jest.mock('expo-crypto', () => {
  let counter = 0;
  return { randomUUID: jest.fn(() => `uuid-${counter++}`) };
});

const mockedPostChat = postChat as jest.Mock;
const mockedAddEventListener = NetInfo.addEventListener as jest.Mock;

function latestNetInfoListener(): (state: { isConnected: boolean }) => void {
  const calls = mockedAddEventListener.mock.calls;
  return calls[calls.length - 1][0];
}

/** Forces a macrotask boundary so every microtask queued by a fire-and-
 * forget async call (the NetInfo listener's retry(...).finally(...))
 * has fully drained before assertions run. */
function flushMicrotasks(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

const renderers: TestRenderer.ReactTestRenderer[] = [];

function renderChatSession(options: Parameters<typeof useChatSession>[0] = {}) {
  let latest: ReturnType<typeof useChatSession>;
  function Host() {
    latest = useChatSession(options);
    return null;
  }
  let renderer: TestRenderer.ReactTestRenderer;
  act(() => {
    renderer = TestRenderer.create(React.createElement(Host));
  });
  renderers.push(renderer!);
  return { current: () => latest };
}

afterEach(() => {
  act(() => {
    for (const renderer of renderers.splice(0)) renderer.unmount();
  });
  jest.clearAllMocks();
});

const OK_REPLY = {
  reply: 'Nice!',
  session_id: 's1',
  skill_id: null,
  intents: [],
  suggested_replies: [],
};

describe('useChatSession -- V4 offline send/retry (005 US3, research.md R9)', () => {
  it('a network failure keeps the message visible, marked failed, rather than removing it', async () => {
    mockedPostChat.mockRejectedValueOnce(new ApiError('network', 'errors.network'));
    const session = renderChatSession();

    await act(async () => {
      await session.current().send('hello offline');
    });

    expect(session.current().messages).toHaveLength(1);
    expect(session.current().messages[0]).toMatchObject({
      content: 'hello offline',
      status: 'failed',
    });
    expect(session.current().draft).toBe(''); // not restored to the composer -- lives on the bubble
  });

  it('manual retry() re-sends the failed message in place and marks it sent on success', async () => {
    mockedPostChat
      .mockRejectedValueOnce(new ApiError('network', 'errors.network'))
      .mockResolvedValueOnce(OK_REPLY);
    const session = renderChatSession();

    await act(async () => {
      await session.current().send('hello offline');
    });
    const failedId = session.current().messages[0].id;

    await act(async () => {
      await session.current().retry(failedId, 'hello offline');
    });

    expect(session.current().messages[0]).toMatchObject({
      content: 'hello offline',
      status: 'sent',
    });
    expect(session.current().messages[1]).toMatchObject({ sender: 'assistant', content: 'Nice!' });
    expect(mockedPostChat).toHaveBeenCalledTimes(2);
  });

  it('reconnect (NetInfo isConnected: true) auto-retries the failed message exactly once', async () => {
    mockedPostChat
      .mockRejectedValueOnce(new ApiError('network', 'errors.network'))
      .mockResolvedValueOnce(OK_REPLY);
    const session = renderChatSession();

    await act(async () => {
      await session.current().send('reconnect test');
    });
    expect(session.current().messages[0].status).toBe('failed');

    await act(async () => {
      latestNetInfoListener()({ isConnected: true });
      await flushMicrotasks();
    });

    expect(mockedPostChat).toHaveBeenCalledTimes(2);
    expect(session.current().messages[0].status).toBe('sent');

    // Firing "online" again must NOT re-send -- the failed ref was cleared on success.
    await act(async () => {
      latestNetInfoListener()({ isConnected: true });
      await flushMicrotasks();
    });
    expect(mockedPostChat).toHaveBeenCalledTimes(2);
  });

  it("web: the browser 'online' event auto-retries even when NetInfo never reports the reconnect", async () => {
    // Chromium + navigator.connection: NetInfo only hears 'change', which a
    // plain offline->online transition doesn't fire (found via Playwright V4).
    const listeners: Record<string, EventListener[]> = {};
    const fakeWindow = {
      addEventListener: jest.fn((type: string, fn: EventListener) => {
        (listeners[type] ??= []).push(fn);
      }),
      removeEventListener: jest.fn(),
    };
    const realWindow = (global as { window?: unknown }).window;
    (global as { window?: unknown }).window = fakeWindow;
    try {
      mockedPostChat
        .mockRejectedValueOnce(new ApiError('network', 'errors.network'))
        .mockResolvedValueOnce(OK_REPLY);
      const session = renderChatSession();

      await act(async () => {
        await session.current().send('online event test');
      });
      expect(session.current().messages[0].status).toBe('failed');

      await act(async () => {
        for (const fn of listeners.online ?? []) fn(new Event('online'));
        await flushMicrotasks();
      });
      expect(mockedPostChat).toHaveBeenCalledTimes(2);
      expect(session.current().messages[0].status).toBe('sent');

      // NetInfo firing too after success must not double-send.
      await act(async () => {
        latestNetInfoListener()({ isConnected: true });
        await flushMicrotasks();
      });
      expect(mockedPostChat).toHaveBeenCalledTimes(2);

      act(() => {
        for (const renderer of renderers.splice(0)) renderer.unmount();
      });
      expect(fakeWindow.removeEventListener).toHaveBeenCalledWith('online', listeners.online[0]);
    } finally {
      (global as { window?: unknown }).window = realWindow;
    }
  });

  it('an offline connectivity event never triggers a retry', async () => {
    mockedPostChat.mockRejectedValueOnce(new ApiError('network', 'errors.network'));
    const session = renderChatSession();

    await act(async () => {
      await session.current().send('still offline');
    });

    await act(async () => {
      latestNetInfoListener()({ isConnected: false });
      await flushMicrotasks();
    });

    expect(mockedPostChat).toHaveBeenCalledTimes(1);
    expect(session.current().messages[0].status).toBe('failed');
  });

  it('a non-network failure (e.g. LLM unavailable) still removes the optimistic bubble and restores the draft, unlike V4', async () => {
    mockedPostChat.mockRejectedValueOnce(new ApiError('llm_unavailable', 'errors.llm_unavailable'));
    const session = renderChatSession();

    await act(async () => {
      await session.current().send('will this work');
    });

    expect(session.current().messages).toHaveLength(0);
    expect(session.current().draft).toBe('will this work');
    expect(session.current().errorKey).toBe('errors.llm_unavailable');
  });
});
