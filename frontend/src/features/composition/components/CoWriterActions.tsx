// LOOM Composition (T3.1) — the co-writer bridge bar. Rendered INSIDE the chat
// providers (as <Chat>'s footer slot) so it can read the live stream: it shows
// Insert-as-draft / Use-as-guide on the LATEST assistant reply (hidden while
// streaming), and starter chips in an empty active thread. Render-only; the chat
// owns the streaming.
import { useTranslation } from 'react-i18next';
import { useChatSession, useChatStream } from '../../chat/providers';

const STARTER_KEYS = ['starter_next', 'starter_character', 'starter_stakes', 'starter_sensory'] as const;

export function CoWriterActions({
  onInsert, onUseAsGuide,
}: {
  onInsert: (text: string) => void;
  onUseAsGuide: (text: string) => void;
}) {
  const { t } = useTranslation('composition');
  const { messages, isStreaming, send } = useChatStream();
  const { activeSession } = useChatSession();

  // Starter chips: only in an active but empty thread (a session exists to send into).
  if (activeSession && messages.length === 0) {
    return (
      <div data-testid="cowriter-starters" className="flex flex-wrap gap-1.5 border-t px-3 py-2">
        <span className="self-center text-[10px] text-muted-foreground/70">{t('cw.starters_hint', { defaultValue: 'try:' })}</span>
        {STARTER_KEYS.map((k) => {
          const prompt = t(`cw.${k}`, { defaultValue: k });
          return (
            <button
              key={k}
              type="button"
              data-testid="cowriter-starter"
              className="rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground hover:border-primary hover:text-primary"
              onClick={() => void send(prompt)}
            >
              {prompt}
            </button>
          );
        })}
      </div>
    );
  }

  // Insert / Use-as-guide on the latest assistant reply (skip the half-streamed one).
  const latest = [...messages].reverse().find((m) => m.role === 'assistant' && m.content.trim().length > 0);
  if (!latest || isStreaming) return null;

  return (
    <div data-testid="cowriter-actions" className="flex flex-wrap gap-2 border-t px-3 py-2">
      <button
        type="button"
        data-testid="cowriter-insert"
        className="rounded border px-2 py-1 text-[11px] hover:border-primary hover:text-primary"
        onClick={() => onInsert(latest.content)}
      >
        ✎ {t('cw.insert', { defaultValue: 'Insert as draft' })}
      </button>
      <button
        type="button"
        data-testid="cowriter-use-guide"
        className="rounded border px-2 py-1 text-[11px] hover:border-primary hover:text-primary"
        onClick={() => onUseAsGuide(latest.content)}
      >
        ⤷ {t('cw.use_as_guide', { defaultValue: 'Use as guide' })}
      </button>
    </div>
  );
}
