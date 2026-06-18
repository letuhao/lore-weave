// LOOM Composition (T3.3 + C17/WG-5) — the editor's inline AI layer: a Classic⇄AI
// mode toggle + a first-class "Continue from cursor" affordance that streams an
// inline ghost at the caret. Mounted inside TiptapEditor via the `aiLayer` slot (gets
// the live editor); the mode is per-device UI state (localStorage). The ghost overlay
// is ANCHOR-based, not mode-gated, so an in-flight stream survives a mode toggle (AC:
// never lose an in-flight stream).
//
// C17 (WG-5): "Continue from cursor" used to be buried behind the AI-mode toggle
// (which defaults to Classic → the action was invisible to a writer continuing an
// existing chapter). It is now PROMINENT and ALWAYS visible — continuing reads as
// continuing, not as a mode you must discover first. It streams operation:'continue'
// grounded on the active scene from the live caret position (useInlineGhost handles
// the empty-doc / caret-at-start / caret-mid + stale-pos edge cases safely).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Editor } from '@tiptap/react';
import { useInlineGhost } from '../hooks/useInlineGhost';
import { InlineGhost } from './InlineGhost';

const MODE_KEY = 'loreweave.editor.aiMode';
type Mode = 'classic' | 'ai';

function readMode(): Mode {
  try { return localStorage.getItem(MODE_KEY) === 'ai' ? 'ai' : 'classic'; } catch { return 'classic'; }
}

export function InlineAiLayer({
  editor, projectId, sceneId, modelRef, modelKind, modelName, token,
}: {
  editor: Editor;
  projectId: string | null;
  sceneId: string | null;
  modelRef: string | null;
  modelKind?: string;
  modelName?: string;
  token: string | null;
}) {
  const { t } = useTranslation('composition');
  const [mode, setMode] = useState<Mode>(readMode);
  const g = useInlineGhost(editor, { projectId, sceneId, modelRef, modelKind, modelName, token });

  const pickMode = (m: Mode) => { setMode(m); try { localStorage.setItem(MODE_KEY, m); } catch { /* private mode */ } };

  const disabledHint = !modelRef
    ? t('inline.need_model', { defaultValue: 'Set a default model in the co-writer Settings' })
    : !sceneId
      ? t('inline.need_scene', { defaultValue: 'Pick a scene in the co-writer panel first' })
      : '';

  return (
    <>
      <div className="absolute right-2 top-2 z-30 flex items-center gap-2 text-[11px]">
        <div role="group" aria-label={t('inline.mode', { defaultValue: 'Writing mode' })} className="flex items-center gap-1 rounded-full border bg-background/90 px-1.5 py-0.5">
          <button
            type="button" data-testid="inline-mode-classic" aria-pressed={mode === 'classic'}
            className={mode === 'classic' ? 'font-medium text-primary' : 'text-muted-foreground'}
            onClick={() => pickMode('classic')}
          >
            {t('inline.mode_classic', { defaultValue: 'Classic' })}
          </button>
          <span aria-hidden className="text-muted-foreground/50">·</span>
          <button
            type="button" data-testid="inline-mode-ai" aria-pressed={mode === 'ai'}
            className={mode === 'ai' ? 'font-medium text-primary' : 'text-muted-foreground'}
            onClick={() => pickMode('ai')}
          >
            {t('inline.mode_ai', { defaultValue: 'AI' })}
          </button>
        </div>
        {/* C17 (WG-5) — first-class "Continue from cursor": ALWAYS visible (not gated
            by mode), prominent (primary fill), explicit handler → caret-anchored
            stream. Direct onClick (no useEffect-for-events). Gated while a ghost is
            pending (g.anchor) so a 2nd Continue can't abandon an un-resolved ghost —
            resolve it (Accept/Discard) first. */}
        <button
          type="button" data-testid="inline-continue"
          className="rounded-full border border-primary bg-primary px-2 py-0.5 font-medium text-primary-foreground disabled:opacity-50"
          disabled={!g.canContinue || g.streaming || !!g.anchor}
          title={disabledHint || t('inline.continueHint', { defaultValue: 'Stream an AI continuation from your cursor.' })}
          onClick={g.continueDraft}
        >
          ✦ {t('inline.continueFromCursor', { defaultValue: 'Continue from cursor' })}
        </button>
      </div>

      {/* anchor-based → a streaming ghost stays visible even if the user toggles Classic */}
      {g.anchor && (
        <InlineGhost
          coords={g.anchor.coords}
          ghost={g.ghost}
          streaming={g.streaming}
          error={g.error}
          onAccept={g.accept}
          onEdit={g.edit}
          onDiscard={g.discard}
          onRegenerate={g.regenerate}
          onReposition={g.reposition}
        />
      )}
    </>
  );
}
