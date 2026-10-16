import NetInfo from '@react-native-community/netinfo';
import * as Crypto from 'expo-crypto';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError, ChatResult, Modality, postChat } from '@/lib/api';

export type ChatMessage = {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  /** V4 (005, research.md R9): a user message that failed to send while
   * offline stays in the transcript (never silently dropped) with a
   * retry affordance, instead of being removed like other send failures. */
  status?: 'sent' | 'failed';
};

/** Format an ISO reset timestamp for interpolation into the localized
 * budget-exhausted copy (005). Falls back to the raw ISO string if
 * Intl formatting fails for any reason -- still informative, never a
 * crash over a nice-to-have. */
function formatResetTime(isoString: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit' }).format(
      new Date(isoString)
    );
  } catch {
    return isoString;
  }
}

/** The LLM's genuine replies are always already-localized free text; only
 * the small set of fixed, non-LLM turns (validation-exhausted degrade,
 * 005's budget-exhausted turn) come back as a raw i18n key needing
 * translation client-side. */
function isI18nKey(reply: string): boolean {
  return reply.startsWith('errors.');
}

type Options = {
  skillId?: string | null;
  newSkillName?: string;
  initialMessages?: ChatMessage[];
  onSkillResolved?: (skillId: string) => void;
};

/** Shared send/optimistic-update logic for both the wizard (skillId=null,
 * newSkillName set) and ongoing skill conversations (skillId set). */
export function useChatSession({
  skillId: initialSkillId = null,
  newSkillName,
  initialMessages = [],
  onSkillResolved,
}: Options) {
  const { t, i18n } = useTranslation();
  const [sessionId] = useState(() => Crypto.randomUUID());
  const [skillId, setSkillId] = useState<string | null>(initialSkillId);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [suggestedReplies, setSuggestedReplies] = useState<string[]>([]);

  // V4: tracks the single most-recently-failed message so reconnect can
  // auto-retry it exactly once; content travels alongside the id so the
  // effect below never needs `messages` as a dependency (which would
  // otherwise churn the NetInfo subscription on every render).
  const failedMessageRef = useRef<{ id: string; content: string } | null>(null);
  const retryInFlightRef = useRef(false);

  const deliver = useCallback(
    async (text: string, modality: Modality, messageId: string) => {
      setSending(true);
      setErrorKey(null);

      try {
        const result: ChatResult = await postChat(text, sessionId, {
          skillId,
          newSkillName: skillId ? undefined : newSkillName,
          modality,
        });
        const replyText = isI18nKey(result.reply)
          ? t(
              result.reply,
              result.budget?.resets_at
                ? { resetTime: formatResetTime(result.budget.resets_at, i18n.language) }
                : undefined
            )
          : result.reply;
        setMessages((prev) => [
          ...prev.map((m) => (m.id === messageId ? { ...m, status: 'sent' as const } : m)),
          { id: Crypto.randomUUID(), sender: 'assistant', content: replyText },
        ]);
        setSuggestedReplies(result.suggested_replies ?? []);
        if (!skillId && result.skill_id) {
          setSkillId(result.skill_id);
          onSkillResolved?.(result.skill_id);
        }
        if (failedMessageRef.current?.id === messageId) failedMessageRef.current = null;
      } catch (error) {
        if (error instanceof ApiError && error.code === 'network') {
          // V4: keep the message, mark it failed with a retry affordance
          // -- never silently dropped, composer stays free for new text.
          setMessages((prev) =>
            prev.map((m) => (m.id === messageId ? { ...m, status: 'failed' as const } : m))
          );
          failedMessageRef.current = { id: messageId, content: text };
        } else {
          // FR-007: other failures keep the draft; remove the optimistic bubble.
          setMessages((prev) => prev.filter((m) => m.id !== messageId));
          setDraft(text);
        }
        setErrorKey(error instanceof ApiError ? error.messageKey : 'errors.internal');
      } finally {
        setSending(false);
      }
    },
    [sessionId, skillId, newSkillName, onSkillResolved, t, i18n]
  );

  const send = useCallback(
    async (overrideText?: string, modality: Modality = 'chat') => {
      const text = (overrideText ?? draft).trim();
      if (!text || sending) return;

      setDraft('');
      setSuggestedReplies([]); // stale once the user has responded (chip or typed)
      const optimisticId = Crypto.randomUUID();
      setMessages((prev) => [...prev, { id: optimisticId, sender: 'user', content: text }]);
      await deliver(text, modality, optimisticId);
    },
    [draft, sending, deliver]
  );

  /** Re-sends a failed message's own content in place (no new bubble,
   * no draft involvement) -- used by both the manual retry affordance and
   * the auto-retry-on-reconnect effect below. */
  const retry = useCallback(
    async (messageId: string, content: string) => {
      if (sending) return;
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, status: undefined } : m))
      );
      await deliver(content, 'chat', messageId);
    },
    [sending, deliver]
  );

  // A ref, not a dependency: NetInfo re-emits the CURRENT connectivity
  // state to every fresh subscriber (its own documented behavior), so if
  // this effect resubscribed whenever `retry`'s identity changes (every
  // send/retry cycle, since it depends on `sending`), a still-failing
  // retry would trigger endless resubscribe -> immediate re-fire -> retry
  // -> fail -> resubscribe... Subscribing exactly once (empty deps) means
  // NetInfo only calls the listener again on a genuine state change.
  const retryRef = useRef(retry);
  useEffect(() => {
    retryRef.current = retry;
  }, [retry]);

  useEffect(() => {
    const retryFailed = () => {
      const failed = failedMessageRef.current;
      if (!failed || retryInFlightRef.current) return;
      retryInFlightRef.current = true;
      retryRef.current(failed.id, failed.content).finally(() => {
        retryInFlightRef.current = false;
      });
    };
    const unsubscribe = NetInfo.addEventListener((state) => {
      if (state.isConnected) retryFailed();
    });
    // Web: where navigator.connection exists (Chromium), NetInfo listens
    // ONLY to its 'change' event, which a plain offline->online transition
    // (e.g. Playwright's setOffline, some OS-level drops) doesn't fire --
    // so the reconnect went unseen. 'online' is the authoritative browser
    // signal; the single-flight guard + cleared failed ref make a double
    // fire (both events) harmless. No-op on native (no window listeners).
    const win = typeof window !== 'undefined' ? window : undefined;
    const canListen = typeof win?.addEventListener === 'function';
    if (canListen) win.addEventListener('online', retryFailed);
    return () => {
      unsubscribe();
      if (canListen) win.removeEventListener('online', retryFailed);
    };
  }, []); // deliberately subscribes exactly once; retryRef.current always has the latest retry

  return {
    messages,
    setMessages,
    draft,
    setDraft,
    send,
    retry,
    sending,
    errorKey,
    sessionId,
    skillId,
    suggestedReplies,
  };
}
