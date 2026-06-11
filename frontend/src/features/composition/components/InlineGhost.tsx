// LOOM Composition (T3.3) — the inline ghost overlay: a position-fixed card at the
// caret showing the streamed continuation + an accept-bar (Accept / Edit / Regenerate
// / Discard). Esc discards; scroll/resize reposition it to follow the caret. The ghost
// is NEVER in the doc until Accept/Edit. Render-only; logic in useInlineGhost.
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

export function InlineGhost({
  coords, ghost, streaming, error, onAccept, onEdit, onDiscard, onRegenerate, onReposition,
}: {
  coords: { top: number; left: number };
  ghost: string;
  streaming: boolean;
  error: string | null;
  onAccept: () => void;
  onEdit: () => void;
  onDiscard: () => void;
  onRegenerate: () => void;
  onReposition: () => void;
}) {
  const { t } = useTranslation('composition');

  useEffect(() => {
    const onScroll = () => onReposition();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onDiscard(); };
    // capture:true catches scroll on inner editor containers, not just window.
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onScroll);
      window.removeEventListener('keydown', onKey);
    };
  }, [onReposition, onDiscard]);

  return (
    <div data-testid="inline-ghost" className="fixed z-40 max-w-[34rem]" style={{ top: coords.top + 4, left: coords.left }}>
      <div className="rounded-md border border-dashed border-indigo-300 bg-indigo-50/95 p-2 text-sm shadow-md dark:border-indigo-700 dark:bg-indigo-950/90">
        <div className="mb-1 text-[10px] uppercase tracking-wide text-indigo-500">
          ✦ {t('inline.drafting', { defaultValue: 'AI · drafting' })}{streaming ? '…' : ''}
        </div>
        <p data-testid="inline-ghost-text" className="whitespace-pre-wrap text-neutral-800 dark:text-neutral-200">
          {ghost}{error && <span className="text-rose-600"> {error}</span>}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
          {streaming ? (
            <button type="button" data-testid="inline-stop" className="rounded bg-rose-600 px-2 py-0.5 text-white" onClick={onDiscard}>
              {t('inline.discard', { defaultValue: 'Esc Discard' })}
            </button>
          ) : (
            <>
              <button type="button" data-testid="inline-accept" className="rounded bg-emerald-600 px-2 py-0.5 text-white disabled:opacity-50" disabled={!ghost} onClick={onAccept}>
                ↵ {t('inline.accept', { defaultValue: 'Accept' })}
              </button>
              <button type="button" data-testid="inline-edit" className="rounded border px-2 py-0.5 disabled:opacity-50" disabled={!ghost} onClick={onEdit}>
                ✎ {t('inline.edit', { defaultValue: 'Edit' })}
              </button>
              <button type="button" data-testid="inline-regenerate" className="rounded border px-2 py-0.5" onClick={onRegenerate}>
                ⟳ {t('inline.regenerate', { defaultValue: 'Regenerate' })}
              </button>
              <button type="button" data-testid="inline-discard" className="rounded border px-2 py-0.5 text-muted-foreground" onClick={onDiscard}>
                {t('inline.discard', { defaultValue: 'Esc Discard' })}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
