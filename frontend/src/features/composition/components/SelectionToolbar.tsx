// LOOM Composition (T3.2) — Selection Tools. A Tiptap floating toolbar over a prose
// selection offering Rewrite / Expand / Describe. Choosing one streams a grounded,
// voice-consistent replacement (reuses useCompositionStream in selection mode) shown
// as a ghost; Accept replaces the saved range, Discard reverts. Self-contained model
// picker (PO). Grounding couples to the compose panel's active scene (sceneContext).
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BubbleMenu } from '@tiptap/react/menus';
import type { Editor } from '@tiptap/react';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useEffectiveModel } from '@/features/chat-ai-settings/context/ChatAiSettingsContext';
import { trackRange, type RangeHandle } from '../../../components/editor/TrackedPositions';
import { useCompositionStream } from '../hooks/useCompositionStream';
import { compositionApi } from '../api';
import type { SelectionOperation } from '../types';
import { MarkErrorBlockAction } from './MarkErrorBlockAction';

export const SELECTION_MAX_CHARS = 8000;
export const SCENE_PLAN_MAX_CHARS = 24000;
const OPS: SelectionOperation[] = ['rewrite', 'expand', 'describe'];

type SceneProposal = { title: string; synopsis: string };

function parseSceneProposals(value: string): SceneProposal[] | null {
  try {
    const parsed = JSON.parse(value) as { scenes?: unknown };
    if (!Array.isArray(parsed.scenes) || parsed.scenes.length === 0 || parsed.scenes.length > 12) return null;
    const scenes = parsed.scenes.map((scene) => {
      const candidate = scene as { title?: unknown; synopsis?: unknown };
      return {
        title: typeof candidate.title === 'string' ? candidate.title.trim() : '',
        synopsis: typeof candidate.synopsis === 'string' ? candidate.synopsis.trim() : '',
      };
    });
    return scenes.every((scene) => scene.title && scene.synopsis) ? scenes : null;
  } catch {
    return null;
  }
}

export function SelectionToolbar({
  editor, projectId, sceneContext, token, chapterId = null,
}: {
  editor: Editor;
  projectId: string;
  sceneContext: string | null;
  token: string | null;
  /** Phase D — the open chapter, so a selection can be MARKED as wrong. Null (or a surface
   *  that doesn't pass it) simply hides the Mark action; it never breaks the AI ops. */
  chapterId?: string | null;
}) {
  const { t } = useTranslation('composition');
  const stream = useCompositionStream(token);
  const [modelRef, setModelRef] = useState('');
  const [instruction, setInstruction] = useState('');
  const [activeOperation, setActiveOperation] = useState<SelectionOperation | null>(null);
  const [selectedProposals, setSelectedProposals] = useState<Set<number>>(new Set());
  const [applyingProposals, setApplyingProposals] = useState(false);
  // The range captured when the op ran — Accept replaces THIS, not the live
  // selection. WS-C: a TRACKED range (PM remaps it through any edit made while the
  // op streams) so Accept targets the correct span even after an edit BEFORE it —
  // the old saved {from,to} + size-check silently inserted at the wrong offset.
  const savedRange = useRef<RangeHandle | null>(null);
  // An op is "active" from click until Accept/Discard — keeps the bubble open even
  // when the streamed ghost has collapsed the visible selection.
  const [active, setActive] = useState(false);

  // Release the tracked range if the toolbar unmounts mid-op (without Accept/Discard)
  // so a stale entry doesn't linger in the shared editor's plugin state.
  useEffect(() => () => { savedRange.current?.release(); savedRange.current = null; }, []);

  // W5 — the shared user-models fetch (active-only, capability=chat; dedupes with
  // every other chat picker in the view via the module cache).
  const models = useUserModels({ capability: 'chat' });
  const modelList = models.models ?? [];
  // Inherit the shared cascade model (spec §8) before falling back to list[0], so
  // this tool matches the chat/studio model instead of an arbitrary favorite.
  const inheritedModel = useEffectiveModel('chat');
  const effectiveModel = modelRef || inheritedModel || modelList[0]?.user_model_id || '';
  const selectedModel = modelList.find((m) => m.user_model_id === effectiveModel);

  const selText = () => {
    const { from, to } = editor.state.selection;
    return editor.state.doc.textBetween(from, to, ' ');
  };
  const selectionLength = selText().length;
  const tooLong = selectionLength > SCENE_PLAN_MAX_CHARS;
  const editTooLong = selectionLength > SELECTION_MAX_CHARS;

  const run = (op: SelectionOperation) => {
    const { from, to } = editor.state.selection;
    const text = editor.state.doc.textBetween(from, to, ' ');
    const limit = op === 'scene_plan' ? SCENE_PLAN_MAX_CHARS : SELECTION_MAX_CHARS;
    if (!text.trim() || text.length > limit || !effectiveModel) return;
    savedRange.current?.release();
    if (op !== 'scene_plan') savedRange.current = trackRange(editor, from, to);
    else savedRange.current = null;
    setActive(true);
    setActiveOperation(op);
    setSelectedProposals(new Set());
    void stream.start({
      projectId,
      selection: text,
      operation: op,
      sceneContext,
      modelSource: 'user_model',
      modelRef: effectiveModel,
      guide: instruction.trim(),
      modelKind: selectedModel?.provider_kind,
      modelName: selectedModel?.provider_model_name,
    });
  };

  useEffect(() => {
    const onContextAi = (event: Event) => {
      const detail = (event as CustomEvent<{ operation?: SelectionOperation; from?: number; to?: number }>).detail;
      if (!detail?.operation || !['rewrite', 'expand', 'describe'].includes(detail.operation)) return;
      if (typeof detail.from !== 'number' || typeof detail.to !== 'number') return;
      editor.chain().focus().setTextSelection({ from: detail.from, to: detail.to }).run();
      run(detail.operation);
    };
    window.addEventListener('lw-editor-context-ai', onContextAi);
    return () => window.removeEventListener('lw-editor-context-ai', onContextAi);
  }, [editor, run]);

  const reset = () => { setActive(false); setActiveOperation(null); setSelectedProposals(new Set()); stream.clearGhost(); savedRange.current?.release(); savedRange.current = null; };
  const discard = () => { stream.stop(); reset(); };
  const accept = () => {
    const handle = savedRange.current;
    if (!handle || !stream.ghost) return;
    // WS-C: the tracked range is remapped through every mid-stream edit; .current()
    // returns null only if the span was deleted/collapsed — the PRECISE stale signal
    // (replaces the crude `to > doc.size` check that missed edits before the range).
    const range = handle.current();
    if (!range) {
      toast.error(t('sel.stale', { defaultValue: 'The selection changed — try again.' }));
      reset();
      return;
    }
    editor.chain().focus().deleteRange(range).insertContentAt(range.from, stream.ghost).run();
    reset();
  };

  const proposals = activeOperation === 'scene_plan' ? parseSceneProposals(stream.ghost) : null;
  const applyProposals = async () => {
    if (!chapterId || !token || !proposals || applyingProposals) return;
    const selected = proposals.filter((_, index) => selectedProposals.has(index));
    if (selected.length === 0) return;
    setApplyingProposals(true);
    try {
      const chapter = await compositionApi.listChapterScenes(projectId, chapterId, token);
      if (!chapter.chapter_node_id) {
        throw new Error(t('sel.scenePlanNeedsOutline', {
          defaultValue: 'This chapter has no outline yet. Create or extract its plan first.',
        }));
      }
      await Promise.all(selected.map((scene) => compositionApi.createNode(
        projectId,
        { kind: 'scene', parent_id: chapter.chapter_node_id!, chapter_id: chapterId, title: scene.title, synopsis: scene.synopsis, status: 'outline' },
        token,
      )));
      reset();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('sel.scenePlanCreateFailed', {
        defaultValue: 'Could not create scene proposals.',
      }));
    } finally {
      setApplyingProposals(false);
    }
  };

  // Keep the menu open while an op is active (ghost pending), else only on a
  // non-empty selection within the cap.
  const shouldShow = ({ editor: ed }: { editor: Editor }) => {
    if (active) return true;
    if (ed.state.selection.empty) return false;
    const selected = ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ');
    return selected.length <= SCENE_PLAN_MAX_CHARS;
  };

  return (
    <BubbleMenu editor={editor} shouldShow={shouldShow} data-testid="selection-bubble">
      <div data-testid="selection-toolbar" className="flex max-w-[22rem] flex-col gap-1.5 rounded-md border bg-popover p-2 text-[11px] shadow-md">
        {active ? (
          <>
            {activeOperation === 'scene_plan' && proposals ? (
              <div data-testid="scene-plan-proposals" className="max-h-48 space-y-1 overflow-y-auto rounded bg-muted/40 p-1.5 text-foreground">
                {proposals.map((scene, index) => (
                  <label key={`${scene.title}-${index}`} className="flex gap-1.5 text-left">
                    <input
                      type="checkbox"
                      data-testid={`scene-plan-proposal-${index}`}
                      checked={selectedProposals.has(index)}
                      onChange={() => setSelectedProposals((current) => {
                        const next = new Set(current);
                        next.has(index) ? next.delete(index) : next.add(index);
                        return next;
                      })}
                    />
                    <span><strong>{scene.title}</strong> — {scene.synopsis}</span>
                  </label>
                ))}
              </div>
            ) : (
              <div data-testid="selection-ghost" className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-muted/40 p-1.5 text-foreground">
                {stream.ghost || (stream.streaming ? t('sel.streaming', { defaultValue: 'Generating…' }) : '')}
                {stream.error && <span className="text-rose-600"> {stream.error}</span>}
              </div>
            )}
            {activeOperation === 'scene_plan' && !stream.streaming && stream.ghost && !proposals && (
              <p data-testid="scene-plan-invalid" className="text-rose-600">{t('sel.scenePlanInvalid', { defaultValue: 'The model did not return valid scene proposals. Try again.' })}</p>
            )}
            <div className="flex items-center gap-1.5">
              {stream.streaming ? (
                <button type="button" data-testid="selection-stop" className="rounded bg-rose-600 px-2 py-0.5 text-white" onClick={discard}>
                  {t('sel.stop', { defaultValue: 'Stop' })}
                </button>
              ) : activeOperation === 'scene_plan' ? (
                <button type="button" data-testid="scene-plan-apply" className="rounded bg-emerald-600 px-2 py-0.5 text-white disabled:opacity-50" disabled={!proposals || selectedProposals.size === 0 || applyingProposals} onClick={() => void applyProposals()}>
                  {applyingProposals ? t('sel.applying', { defaultValue: 'Creating…' }) : t('sel.createScenes', { defaultValue: 'Create selected scenes' })}
                </button>
              ) : (
                <button type="button" data-testid="selection-accept" className="rounded bg-emerald-600 px-2 py-0.5 text-white disabled:opacity-50" disabled={!stream.ghost} onClick={accept}>
                  {t('sel.accept', { defaultValue: 'Accept' })}
                </button>
              )}
              <button type="button" data-testid="selection-discard" className="rounded border px-2 py-0.5 text-muted-foreground" onClick={discard}>
                {t('sel.discard', { defaultValue: 'Discard' })}
              </button>
            </div>
          </>
        ) : tooLong ? (
          <span data-testid="selection-too-long" className="text-amber-600">
            {t('sel.too_long', { defaultValue: 'Selection too long for AI tools.' })}
          </span>
        ) : (
          <>
            <div className="flex items-center gap-1.5">
              {/* W5 — shared ModelPicker (compact) replaces the bespoke <select>. */}
              <div data-testid="selection-model" className="min-w-0 flex-1">
                <ModelPicker
                  capability="chat"
                  compact
                  value={effectiveModel || null}
                  onChange={(id) => setModelRef(id ?? '')}
                  ariaLabel={t('sel.model', { defaultValue: 'Model' })}
                  placeholder={t('sel.no_model', { defaultValue: 'No model' })}
                />
              </div>
            </div>
            <input
              data-testid="selection-instruction"
              aria-label={t('sel.instruction', { defaultValue: 'Optional instruction' })}
              placeholder={t('sel.instruction', { defaultValue: 'e.g. terser…' })}
              className="rounded border bg-background px-1 py-0.5"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <div className="flex items-center gap-1.5">
              {OPS.map((op) => (
                <button
                  key={op}
                  type="button"
                  data-testid={`selection-${op}`}
                  className="rounded border px-2 py-0.5 hover:border-primary hover:text-primary disabled:opacity-40"
                  disabled={!effectiveModel || editTooLong}
                  onClick={() => run(op)}
                >
                  ✦ {t(`sel.${op}`, { defaultValue: op })}
                </button>
              ))}
              <button
                type="button"
                data-testid="selection-scene-plan"
                className="rounded border px-2 py-0.5 hover:border-primary hover:text-primary disabled:opacity-40"
                disabled={!effectiveModel || !chapterId || tooLong}
                onClick={() => run('scene_plan')}
              >
                ✦ {t('sel.scenePlan', { defaultValue: 'Suggest scenes' })}
              </button>
              {editTooLong && !tooLong && (
                <span data-testid="scene-plan-long-selection" className="text-amber-600">
                  {t('sel.scenePlanOnly', { defaultValue: 'This selection is available for scene suggestions only.' })}
                </span>
              )}
              {/* Phase D — record that this passage is WRONG, with a note the co-writer acts
                  on later. Not an AI op: it needs no model, so it stays enabled when none is
                  picked (the ops above are disabled without one). */}
              <MarkErrorBlockAction
                editor={editor}
                projectId={projectId}
                chapterId={chapterId}
                token={token}
              />
            </div>
          </>
        )}
      </div>
    </BubbleMenu>
  );
}
