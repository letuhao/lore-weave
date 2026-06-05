// LOOM Composition (M8) — compose-bar + ghost stream + inline critic (view).
//
// The streamed prose lives in the hook's FE-LOCAL `ghost` buffer and is shown as
// a ghost preview — it is NOT in the editor doc and is NEVER autosaved until the
// author clicks Accept (§13 SC4), which calls onAccept() to insert it and then
// runs an advisory critique.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useCompositionStream } from '../hooks/useCompositionStream';
import { useCritique } from '../hooks/useCritique';
import { useAutoGenerate, useCorrection } from '../hooks/useAutoGenerate';
import { CandidatesView } from './CandidatesView';
import type { CorrectionBody, Critic } from '../types';

type ReasoningPref = 'off' | 'auto' | 'low' | 'medium' | 'high';

type Props = {
  projectId: string;
  sceneId: string;
  modelRef: string;
  modelKind?: string;
  modelName?: string;
  token: string | null;
  onAccept: (text: string) => void;
};

export function ComposeView({ projectId, sceneId, modelRef, modelKind, modelName, token, onAccept }: Props) {
  const { t } = useTranslation('composition');
  const [guide, setGuide] = useState('');
  // Reasoning preference. "auto" lets the server decide per the selected model
  // (adaptive pass-through vs our rule-based scorer); off/low/medium/high are
  // explicit overrides.
  const [reasoning, setReasoning] = useState<ReasoningPref>('auto');
  // Diverge = controlled-auto gate (K options). OFF = V0 live token stream.
  const [diverge, setDiverge] = useState(false);
  const stream = useCompositionStream(token);
  const auto = useAutoGenerate(token);
  const correction = useCorrection(token);
  const { critique, dismiss } = useCritique(token);

  const busy = stream.streaming || auto.isPending;
  const canGenerate = !!sceneId && !!modelRef && !busy;
  const genParams = {
    projectId, outlineNodeId: sceneId, modelSource: 'user_model' as const, modelRef, guide,
    reasoning, modelKind, modelName,
  };
  const generate = () => (diverge ? auto.mutate(genParams) : stream.start(genParams));

  const accept = () => {
    if (!stream.ghost) return;
    onAccept(stream.ghost);
    if (stream.jobId) critique.mutate({ jobId: stream.jobId, passage: stream.ghost });
    stream.clearGhost();
  };

  // ── controlled-auto (diverge) gate handlers ──
  // Accepting a candidate (winner / picked / edited) inserts it + runs the
  // advisory critique on the auto job, then clears the cards. Correction capture
  // is fire-and-forget — it never blocks the insert.
  const acceptText = (text: string) => {
    onAccept(text);
    if (auto.data?.job_id) critique.mutate({ jobId: auto.data.job_id, passage: text });
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

  const critic: Critic = critique.data?.critic ?? null;

  return (
    <div className="flex flex-col gap-2 p-3">
      <textarea
        className="w-full resize-none rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-600"
        rows={2}
        placeholder={t('guidePlaceholder', { defaultValue: 'Optional guidance for the co-writer…' })}
        value={guide}
        onChange={(e) => setGuide(e.target.value)}
      />
      <div className="flex items-center gap-2">
        <select
          data-testid="compose-reasoning"
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value as ReasoningPref)}
          aria-label={t('reasoning', { defaultValue: 'Reasoning' })}
          title={t('reasoningHint', { defaultValue: 'Auto = the server decides per model. Off disables thinking; Low/Med/High force it.' })}
        >
          <option value="auto">{t('reasoningAuto', { defaultValue: 'Thinking: auto' })}</option>
          <option value="off">{t('reasoningOff', { defaultValue: 'Thinking: off' })}</option>
          <option value="low">{t('reasoningLow', { defaultValue: 'Thinking: low' })}</option>
          <option value="medium">{t('reasoningMedium', { defaultValue: 'Thinking: med' })}</option>
          <option value="high">{t('reasoningHigh', { defaultValue: 'Thinking: high' })}</option>
        </select>
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
              <button data-testid="compose-regenerate" className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={generate}>
                {t('regenerate', { defaultValue: 'Regenerate' })}
              </button>
              <button data-testid="compose-discard" className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={stream.clearGhost}>
                {t('discard', { defaultValue: 'Discard' })}
              </button>
            </div>
          )}
        </div>
      )}

      {critic && <CriticFlags critic={critic} jobId={stream.jobId} onDismiss={(ruleId) => stream.jobId && dismiss.mutate({ jobId: stream.jobId, ruleId })} />}
    </div>
  );
}

function CriticFlags({ critic, onDismiss }: { critic: NonNullable<Critic>; jobId: string | null; onDismiss: (ruleId: string) => void }) {
  const { t } = useTranslation('composition');
  const dims: [string, number | null][] = [
    ['coherence', critic.coherence], ['voice_match', critic.voice_match],
    ['pacing', critic.pacing], ['canon_consistency', critic.canon_consistency],
  ];
  return (
    <div data-testid="compose-critic" className="rounded border border-neutral-200 p-2 text-xs dark:border-neutral-700">
      <div className="mb-1 font-medium">{t('critic', { defaultValue: 'Critic (advisory)' })}</div>
      {critic.error ? (
        <div className="text-neutral-500">{t('criticUnavailable', { defaultValue: 'Critic unavailable.' })}</div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {dims.map(([k, v]) => (
            <span key={k} className="rounded bg-neutral-100 px-1.5 py-0.5 dark:bg-neutral-800">
              {t(k, { defaultValue: k })}: {v ?? '—'}
            </span>
          ))}
        </div>
      )}
      {(critic.violations ?? []).map((vio) => (
        <div key={vio.rule_id} className={`mt-1 rounded bg-amber-50 p-1.5 dark:bg-amber-950 ${vio.dismissed ? 'opacity-50 line-through' : ''}`}>
          <span className="text-amber-800 dark:text-amber-300">{vio.why || vio.span}</span>
          {!vio.dismissed && (
            <button className="ml-2 text-[11px] text-neutral-500 underline" onClick={() => onDismiss(vio.rule_id)}>
              {t('dismiss', { defaultValue: 'dismiss' })}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
