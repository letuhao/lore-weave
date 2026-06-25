// LOOM Composition (WS-B1) — the standing Continuity Critic panel (a dockable
// `critic` SubTab). Surfaces the latest generation's advisory verdict
// (coherence/voice/pacing/canon + the C26 derivative override-gate) + the
// canon-gate result, and offers a "re-check current draft" action.
//
// Sources, in precedence order:
//   1. a fresh in-panel re-check (the critique mutation result), then
//   2. the shared CriticStateContext verdict (dock/float — written by ComposeView /
//      ChapterAssembleView in the SAME root), then
//   3. a re-fetch of the latest stored verdict by jobId (the POPPED-OUT case — a
//      separate root where the context doesn't reach; the jobId comes from the
//      SharedWorker-backed live stream, which IS shared across windows).
// Read-only for canon (no generate control here → CanonGatePanel without Revise).
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { compositionApi } from '../api';
import { useLiveStreamOptional } from '../context/LiveStateContext';
import { useCriticStateOptional } from '../context/CriticStateContext';
import { useCritique } from '../hooks/useCritique';
import { CriticFlags } from './CriticFlags';
import { CanonGatePanel } from './CanonGatePanel';
import type { CriticVerdict } from '../context/CriticStateContext';

export function CriticPanel({ token }: { token: string | null }) {
  const { t } = useTranslation('composition');
  const shared = useCriticStateOptional();
  const stream = useLiveStreamOptional();
  const jobId = shared?.verdict?.jobId ?? stream?.jobId ?? null;
  const { critique, dismiss } = useCritique(token);

  // Popout / fresh-root case (no in-memory shared verdict): re-fetch the latest
  // STORED verdict by jobId. Skipped when the shared store already holds it.
  const refetch = useQuery({
    queryKey: ['composition', 'critic-verdict', jobId],
    queryFn: () => compositionApi.getJob(jobId!, token!),
    enabled: !shared?.verdict && !!jobId && !!token,
  });

  // Resolve which verdict to render: live re-check > shared store > re-fetched job.
  // canon is only available via the shared store (the polled GenerationJob carries
  // no canon); a popped-out panel shows the critic dims + gate, canon stays null.
  const verdict: CriticVerdict | null =
    critique.data?.critic
      ? { critic: critique.data.critic, canon: shared?.verdict?.canon ?? null, jobId }
      : shared?.verdict
        ? shared.verdict
        : refetch.data?.critic
          ? { critic: refetch.data.critic, canon: null, jobId }
          : null;

  const recheck = () => {
    if (stream?.jobId && stream.ghost) critique.mutate({ jobId: stream.jobId, passage: stream.ghost });
  };

  return (
    <div data-testid="critic-panel" className="flex h-full flex-col gap-2 overflow-auto p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium">{t('critic', { defaultValue: 'Critic (advisory)' })}</div>
        <button
          type="button"
          data-testid="critic-recheck"
          className="shrink-0 rounded border border-neutral-300 px-2 py-0.5 text-xs disabled:opacity-50 dark:border-neutral-600"
          disabled={!stream?.jobId || !stream.ghost || critique.isPending}
          onClick={recheck}
        >
          {critique.isPending
            ? t('criticRechecking', { defaultValue: 'Re-checking…' })
            : t('criticRecheck', { defaultValue: 'Re-check current draft' })}
        </button>
      </div>
      {verdict && (verdict.critic || verdict.canon) ? (
        <>
          {verdict.critic && (
            <CriticFlags
              critic={verdict.critic}
              jobId={verdict.jobId}
              onDismiss={(ruleId) => verdict.jobId && dismiss.mutate({ jobId: verdict.jobId, ruleId })}
            />
          )}
          {verdict.canon && <CanonGatePanel canon={verdict.canon} />}
        </>
      ) : (
        <div data-testid="critic-empty" className="text-xs text-neutral-500">
          {refetch.isLoading
            ? t('loading', { defaultValue: 'Loading…' })
            : t('criticPanelEmpty', { defaultValue: 'No verdict yet — generate a scene (or re-check the current draft) to see the continuity critic.' })}
        </div>
      )}
    </div>
  );
}
