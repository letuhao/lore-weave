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

  const pickMode = (m: Mode) => {
    setMode(m);
    try { localStorage.setItem(MODE_KEY, m); } catch { /* private mode */ }
    window.dispatchEvent(new CustomEvent('lw-editor-mode-change', { detail: { mode: m } }));
  };

  // T2 — why Continue is disabled, as a SPECIFIC reason the user can act on.
  //
  // This used to resolve only the model/scene pair and live exclusively in `title`. A `title`
  // tooltip on a `disabled` button is the one place a reason cannot be discovered: most browsers
  // suppress the tooltip, and a disabled control invites no hover in the first place. A 2026-09-06
  // human-sim run spent an entire 5-arc novel hand-pasting prose having concluded the feature did
  // not exist — it existed, and `modelRef` was simply null the whole time.
  //
  // `modelRef` is null unless the Work has a persisted `settings.default_model_ref` OR the user
  // happens to have exactly one chat model, so "several models registered, no default chosen" —
  // an ordinary state — disables the button forever with no visible cause.
  //
  // Deliberately NOT auto-picking a model: per settings-and-config SET-1..8 a default model is a
  // user setting, and silently choosing one on their behalf is the "silent fallback" that standard
  // forbids. Name the gap, point at where it is fixed, let the author decide.
  const disabledReason: { text: string; key: string } | null = !modelRef
    ? {
        key: 'need-model',
        text: t('inline.need_model', {
          defaultValue: 'No default model set for this book — pick one in the co-writer panel’s Settings to enable AI continuation.',
        }),
      }
    : !sceneId
      ? {
          key: 'need-scene',
          text: t('inline.need_scene', {
            defaultValue: 'No scene selected — pick a scene in the co-writer panel first.',
          }),
        }
      : !editor
        ? {
            key: 'need-editor',
            text: t('inline.need_editor', { defaultValue: 'The editor is still loading.' }),
          }
        : g.streaming
          ? {
              key: 'streaming',
              text: t('inline.streaming', { defaultValue: 'Writing… let the current continuation finish.' }),
            }
          : g.anchor
            ? {
                key: 'pending-ghost',
                text: t('inline.pending_ghost', {
                  defaultValue: 'Accept or discard the current suggestion before starting another.',
                }),
              }
            : null;
  const disabledHint = disabledReason?.text ?? '';

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

      {/* T2 — the reason, VISIBLE. `title` alone was unreachable on a disabled control (see the
          comment on disabledReason). Rendered as a sibling of the toolbar so it cannot be clipped
          by the button row, and marked role="status" so it reaches assistive tech too. */}
      {disabledReason && (
        <div
          role="status"
          data-testid="inline-continue-disabled-reason"
          data-reason={disabledReason.key}
          className="absolute right-2 top-9 z-30 max-w-[22rem] rounded-md border bg-background/95 px-2 py-1 text-right text-[11px] leading-snug text-muted-foreground shadow-sm"
        >
          {disabledReason.text}
        </div>
      )}

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
