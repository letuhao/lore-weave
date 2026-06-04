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
import type { Critic } from '../types';

type Props = {
  projectId: string;
  sceneId: string;
  modelRef: string;
  token: string | null;
  onAccept: (text: string) => void;
};

export function ComposeView({ projectId, sceneId, modelRef, token, onAccept }: Props) {
  const { t } = useTranslation('composition');
  const [guide, setGuide] = useState('');
  // Reasoning knob — "auto" = model default; "none" disables hidden thinking so
  // a reasoning-model drafter spends its budget on prose, not reasoning tokens.
  const [reasoning, setReasoning] = useState<'auto' | 'none'>('auto');
  const stream = useCompositionStream(token);
  const { critique, dismiss } = useCritique(token);

  const canGenerate = !!sceneId && !!modelRef && !stream.streaming;
  const generate = () =>
    stream.start({
      projectId, outlineNodeId: sceneId, modelSource: 'user_model', modelRef, guide,
      reasoningEffort: reasoning === 'none' ? 'none' : undefined,
    });

  const accept = () => {
    if (!stream.ghost) return;
    onAccept(stream.ghost);
    if (stream.jobId) critique.mutate({ jobId: stream.jobId, passage: stream.ghost });
    stream.clearGhost();
  };

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
          onChange={(e) => setReasoning(e.target.value as 'auto' | 'none')}
          aria-label={t('reasoning', { defaultValue: 'Reasoning' })}
          title={t('reasoningHint', { defaultValue: 'Off = disable hidden thinking (faster, needed for reasoning models)' })}
        >
          <option value="auto">{t('reasoningAuto', { defaultValue: 'Thinking: auto' })}</option>
          <option value="none">{t('reasoningOff', { defaultValue: 'Thinking: off' })}</option>
        </select>
        {!stream.streaming ? (
          <button
            data-testid="compose-generate"
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={!canGenerate}
            onClick={generate}
          >
            {t('generate', { defaultValue: 'Generate' })}
          </button>
        ) : (
          <button className="rounded bg-red-600 px-3 py-1.5 text-sm text-white" onClick={stream.stop}>
            {t('stop', { defaultValue: 'Stop' })}
          </button>
        )}
        {!sceneId && <span className="self-center text-xs text-amber-600">{t('needScene', { defaultValue: 'Pick a scene' })}</span>}
        {sceneId && !modelRef && <span className="self-center text-xs text-amber-600">{t('needModel', { defaultValue: 'Pick a model' })}</span>}
      </div>

      {stream.error && <div className="rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950">{stream.error}</div>}

      {/* ghost preview (FE-local, not in the doc, not autosaved) */}
      {(stream.streaming || stream.ghost) && (
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
              <button className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={generate}>
                {t('regenerate', { defaultValue: 'Regenerate' })}
              </button>
              <button className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600" onClick={stream.clearGhost}>
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
