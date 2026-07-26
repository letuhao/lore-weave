// LOOM Composition (M8) — compose-bar + ghost stream + inline critic (view).
//
// The streamed prose lives in the hook's FE-LOCAL `ghost` buffer and is shown as
// a ghost preview — it is NOT in the editor doc and is NEVER autosaved until the
// author clicks Accept (§13 SC4), which calls onAccept() to insert it and then
// runs an advisory critique.
import type { Dispatch, SetStateAction } from 'react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLiveStream } from '../context/LiveStateContext';
import { useCriticStateOptional } from '../context/CriticStateContext';
import { useCritique } from '../hooks/useCritique';
import { useAutoGenerate, useCorrection } from '../hooks/useAutoGenerate';
import { CandidatesView } from './CandidatesView';
import { CanonGatePanel } from './CanonGatePanel';
import { CriticFlags } from './CriticFlags';
import type { CanonViolation, CorrectionBody, Critic } from '../types';
import { EffortSelect, type EffortLevel } from '@/components/ai-task';

type Props = {
  projectId: string;
  sceneId: string;
  modelRef: string;
  modelKind?: string;
  modelName?: string;
  token: string | null;
  // Returns TRUE only when the prose actually landed in the editor. We clear the ghost / cards ONLY
  // on true, so a failed insert (no editor open on this chapter in the studio dock) keeps the draft
  // instead of dropping it (the legacy co-mounted path always returns true).
  onAccept: (text: string) => boolean;
  /** T3.1: the compose guide is lifted to CompositionPanel so the co-writer chat's
   *  "Use as guide" can pre-fill it. A SetStateAction setter so the canon-revise
   *  append (functional updater) keeps working. */
  guide: string;
  onGuideChange: Dispatch<SetStateAction<string>>;
  /** M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — when true, offer the "✦ Adapt from source"
   *  action (the open Work is a derivative, the scene is at/after branch_point, and the
   *  source chapter has prose). Computed by CompositionPanel via useAdaptFromSource. */
  canAdapt?: boolean;
  /** M1 — derivative + at/after branch but the source chapter is empty → show a
   *  "nothing to adapt" hint instead of the action (no silent weak generation). */
  adaptSourceEmpty?: boolean;
};

export function ComposeView({ projectId, sceneId, modelRef, modelKind, modelName, token, onAccept, guide, onGuideChange, canAdapt, adaptSourceEmpty }: Props) {
  const { t } = useTranslation('composition');
  const guideRef = useRef<HTMLTextAreaElement>(null);
  // Reasoning preference. "auto" lets the server decide per the selected model
  // (adaptive pass-through vs our rule-based scorer); off/low/medium/high are
  // explicit overrides.
  const [reasoning, setReasoning] = useState<EffortLevel>('auto');
  // Diverge = controlled-auto gate (K options). OFF = V0 live token stream.
  const [diverge, setDiverge] = useState(false);
  // T5.4 — the co-writer stream is HOISTED to LiveStateProvider (above the windowing
  // layer) so a docked/floated/popped Compose keeps streaming through a move. The
  // `token` prop is retained for the other (non-hoisted) hooks below.
  const stream = useLiveStream();
  const auto = useAutoGenerate(token);
  const correction = useCorrection(token);
  const { critique, dismiss } = useCritique(token);
  // WS-B1 — lift the verdict to the shared store so the standing `critic` SubTab
  // panel (a dock sibling) renders it. Optional: null when there's no provider.
  const criticState = useCriticStateOptional();

  const busy = stream.streaming || auto.isPending;
  const canGenerate = !!sceneId && !!modelRef && !busy;
  const genParams = {
    projectId, outlineNodeId: sceneId, modelSource: 'user_model' as const, modelRef, guide,
    reasoning, modelKind, modelName,
  };
  const generate = () => (diverge ? auto.mutate(genParams) : stream.start(genParams));
  // M1 — adapt the inherited SOURCE scene through the divergence. Same surface as a
  // normal generate (diverge → K cards; else → ghost), just the `adapt_scene` op: the
  // BE fires gather_source_scene + a no-auto-insert ghost the writer accepts manually.
  const adapt = () => {
    const p = { ...genParams, operation: 'adapt_scene' as const };
    return diverge ? auto.mutate(p) : stream.start(p);
  };

  const accept = () => {
    if (!stream.ghost) return;
    if (!onAccept(stream.ghost)) return; // insert failed (no editor) — keep the ghost, don't critique/clear
    if (stream.jobId) {
      const jobId = stream.jobId;
      critique.mutate(
        { jobId, passage: stream.ghost },
        { onSuccess: (data) => data.critic && criticState?.setVerdict({ critic: data.critic, canon: null, jobId }) },
      );
    }
    stream.clearGhost();
  };

  // ── controlled-auto (diverge) gate handlers ──
  // Accepting a candidate (winner / picked / edited) inserts it + runs the
  // advisory critique on the auto job, then clears the cards. Correction capture
  // is fire-and-forget — it never blocks the insert.
  const acceptText = (text: string) => {
    if (!onAccept(text)) return; // insert failed (no editor) — keep the cards, don't critique/reset
    if (auto.data?.job_id) {
      const jobId = auto.data.job_id;
      const canon = auto.data.canon ?? null;
      critique.mutate(
        { jobId, passage: text },
        { onSuccess: (data) => data.critic && criticState?.setVerdict({ critic: data.critic, canon, jobId }) },
      );
    }
    auto.reset();
  };
  const correct = (body: CorrectionBody) => {
    if (auto.data?.job_id) correction.mutate({ jobId: auto.data.job_id, body });
  };
  const regenerate = () => {
    correct({ kind: 'regenerate', guidance: guide });
    auto.mutate(genParams); // re-run with the same guidance; replaces the cards
  };
  const rejectAll = () => { correct({ kind: 'reject' }); auto.reset(); };
  const toggleDiverge = (on: boolean) => { setDiverge(on); auto.reset(); stream.clearGhost(); };

  // ── A2-S4a: canon Revise — the author steers a re-generate. Pre-fill the guide
  // with the violation context + focus the box (PO decision: author steers, not a
  // one-click re-run). Appended (newline-sep) so any existing guidance is kept.
  const revise = (v: CanonViolation) => {
    const name = v.name || v.matched || v.entity_id;
    const line =
      t('reviseGuide', {
        defaultValue:
          'Keep canon consistent: {{name}} is gone from the story by this scene — do not portray them as present or acting.',
        name,
      }) + (v.why ? ` (${v.why})` : '');
    onGuideChange((prev) => (prev.trim() ? `${prev.trim()}\n${line}` : line));
    guideRef.current?.focus();
  };

  // ── V0 cowrite-stream gate capture (slice 5) ──
  // Accepting the single stream ghost as-is is NOT a correction (H2; the inline
  // ghost is not editable, so a post-accept editor edit isn't cleanly captured).
  // Regenerate + Discard ARE genuine dissatisfaction signals → capture them so
  // the eval-gate dashboard has a real cowrite baseline to compare auto against.
  const cowriteCorrect = (body: CorrectionBody) => {
    if (stream.jobId) correction.mutate({ jobId: stream.jobId, body });
  };
  const cowriteRegenerate = () => { cowriteCorrect({ kind: 'regenerate', guidance: guide }); generate(); };
  const cowriteDiscard = () => { cowriteCorrect({ kind: 'reject' }); stream.clearGhost(); };

  const critic: Critic = critique.data?.critic ?? null;

  return (
    <div className="flex flex-col gap-2 p-3">
      <textarea
        ref={guideRef}
        className="w-full resize-none rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-600"
        rows={2}
        placeholder={t('guidePlaceholder', { defaultValue: 'Optional guidance for the co-writer…' })}
        value={guide}
        onChange={(e) => onGuideChange(e.target.value)}
      />
      <div className="flex items-center gap-2">
        {/* Shared AI-task EffortSelect (unified 5-level vocab) — was a raw <select> */}
        <EffortSelect value={reasoning} onChange={setReasoning} />
        {stream.reasoning && (
          <span data-testid="compose-reasoning-badge" className="self-center rounded bg-neutral-100 px-1.5 py-0.5 text-[11px] text-neutral-500 dark:bg-neutral-800">
            {stream.reasoning.source === 'adaptive'
              ? t('reasoningResolvedAdaptive', { defaultValue: 'model decides' })
              : stream.reasoning.source === 'non_reasoning'
                ? t('reasoningResolvedNone', { defaultValue: 'no thinking' })
                : t('reasoningResolved', { defaultValue: '{{source}} → {{effort}}', source: stream.reasoning.source, effort: stream.reasoning.effort ?? '—' })}
          </span>
        )}
        <label data-testid="compose-diverge-toggle" className="flex items-center gap-1 text-xs text-neutral-600 dark:text-neutral-300" title={t('divergeHint', { defaultValue: 'Generate several options and pick/edit the best (non-streaming).' })}>
          <input type="checkbox" checked={diverge} onChange={(e) => toggleDiverge(e.target.checked)} />
          {t('diverge', { defaultValue: 'Diverge (K options)' })}
        </label>
        {stream.streaming ? (
          <button data-testid="compose-stop" className="rounded bg-red-600 px-3 py-1.5 text-sm text-white" onClick={stream.stop}>
            {t('stop', { defaultValue: 'Stop' })}
          </button>
        ) : (
          <button
            data-testid="compose-generate"
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={!canGenerate}
            onClick={generate}
          >
            {auto.isPending ? t('generating', { defaultValue: 'Generating…' }) : t('generate', { defaultValue: 'Generate' })}
          </button>
        )}
        {/* M1 — adapt the inherited source scene through the divergence (derivative,
            at/after branch, source has prose). Sits beside Generate; same ghost/cards
            surface. Hidden while a stream is mid-flight (the Stop button owns that). */}
        {canAdapt && !stream.streaming && (
          <button
            type="button" data-testid="compose-adapt"
            className="rounded border border-purple-400 px-3 py-1.5 text-sm text-purple-700 hover:bg-purple-50 disabled:opacity-50 dark:border-purple-600 dark:text-purple-300 dark:hover:bg-purple-950/30"
            disabled={!canGenerate}
            title={t('derive.adapt.hint', { defaultValue: 'Rewrite the inherited source scene to honour this branch (a ghost you review and accept).' })}
            onClick={adapt}
          >
            ✦ {t('derive.adapt.action', { defaultValue: 'Adapt from source' })}
          </button>
        )}
        {adaptSourceEmpty && !canAdapt && (
          <span data-testid="compose-adapt-empty" className="self-center text-xs text-muted-foreground" title={t('derive.adapt.emptyHint', { defaultValue: 'The source chapter has no prose to adapt — generate a fresh draft instead.' })}>
            {t('derive.adapt.empty', { defaultValue: 'Nothing to adapt' })}
          </span>
        )}
        {!sceneId && <span data-testid="compose-need-scene" className="self-center text-xs text-amber-600">{t('needScene', { defaultValue: 'Pick a scene' })}</span>}
        {sceneId && !modelRef && <span data-testid="compose-need-model" className="self-center text-xs text-amber-600">{t('needModel', { defaultValue: 'Pick a model' })}</span>}
      </div>

      {!diverge && stream.error && <div className="rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950">{stream.error}</div>}

      {/* controlled-auto gate: all K options as cards (non-streaming). */}
      {diverge && auto.isError && (
        <div data-testid="compose-auto-error" className="rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950">
          {t('generateFailed', { defaultValue: 'Generation failed — try again.' })}
        </div>
      )}
      {/* A2-S4a canon gate verdict on the converged winner (hard/advisory/unchecked). */}
      {diverge && auto.data?.canon && !auto.isPending && (
        <CanonGatePanel canon={auto.data.canon} onRevise={revise} />
      )}
      {diverge && auto.data && !auto.isPending && (auto.data.candidates?.length ?? 0) > 0 && (
        <CandidatesView
          gen={auto.data}
          busy={correction.isPending}
          onAcceptText={acceptText}
          onCorrect={correct}
          onRegenerate={regenerate}
          onReject={rejectAll}
        />
      )}

      {/* ghost preview (FE-local, not in the doc, not autosaved) — V0 stream only */}
      {!diverge && (stream.streaming || stream.ghost) && (
        <div className="rounded border border-dashed border-indigo-300 bg-indigo-50/40 p-2 text-sm dark:border-indigo-700 dark:bg-indigo-950/30">
          <div className="mb-1 text-xs uppercase tracking-wide text-indigo-500">
            {t('ghost', { defaultValue: 'Ghost draft' })}{stream.streaming ? '…' : ''}
          </div>
          <p data-testid="compose-ghost" className="whitespace-pre-wrap text-neutral-800 dark:text-neutral-200">{stream.ghost}</p>
          {!stream.streaming && stream.ghost && (
            <div className="mt-2 flex gap-2">
              <button data-testid="compose-accept" className="rounded bg-emerald-600 px-2.5 py-1 text-xs text-white" onClick={accept}>
                {t('accept', { defaultValue: 'Accept' })}
              </button>
              <button data-testid="compose-regenerate" className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={cowriteRegenerate}>
                {t('regenerate', { defaultValue: 'Regenerate' })}
              </button>
              <button data-testid="compose-discard" className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={cowriteDiscard}>
                {t('discard', { defaultValue: 'Discard' })}
              </button>
            </div>
          )}
        </div>
      )}

      {critic && <CriticFlags critic={critic} jobId={stream.jobId} onRegenerate={cowriteRegenerate} onDismiss={(ruleId) => stream.jobId && dismiss.mutate({ jobId: stream.jobId, ruleId })} />}
    </div>
  );
}

