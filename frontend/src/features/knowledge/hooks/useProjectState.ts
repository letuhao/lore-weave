import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type ExtractionJobScopeWire,
  type ExtractionJobWire,
  type GraphStatsResponse,
} from '../api';
import type { Project } from '../types';
import type {
  ProjectMemoryState,
  ExtractionJobSummary,
  GraphStats,
  JobScope,
  ExtractionJobStatus,
} from '../types/projectState';
import type { ProjectStateCardActions } from '../components/ProjectStateCard';

// K19a.4 — hook that derives ProjectMemoryState from (Project, active jobs,
// graph stats). See KSA §8.4 for the state machine. The hook is per-project:
// the caller (ProjectsTab) runs one per row.
//
// Scope: derives every state reachable from BE signals — `disabled`,
// `building_running`, `building_paused_{user,budget,error}`, `complete`,
// `failed`. `cancelling`, `deleting`, `model_change_pending`, `stale` are
// deferred (signals not yet plumbed). `estimating` / `ready_to_build` are
// dialog-internal and never produced here.
//
// Callbacks (14 total): 9 real actions fire BE APIs directly, 5
// dialog/confirm-dependent (`onBuildGraph`/`onStart`/`onViewError`
// from K19a.5 + `onChangeModel`/`onDisable` from K19a.6) are silent
// no-ops that the parent (ProjectRow) merges overrides on top of.
// Real actions are wrapped in try/catch + toast.error so BE failures
// surface visibly (review-impl F2 from K19a.4).

const POLL_INTERVAL_MS = 2000;

// K19a.7 review-impl F1 — centralise the action i18n keys so a typo in a
// callsite fails at compile time rather than rendering a raw key path in
// production (i18next silently falls back to the key when missing). The
// runtime iterator in projectState.test.ts covers resource presence; this
// map covers callsite spelling.
const ACTION_KEYS = {
  pause: 'projects.state.actions.pause',
  resume: 'projects.state.actions.resume',
  cancel: 'projects.state.actions.cancel',
  retry: 'projects.state.actions.retry',
  deleteGraph: 'projects.state.actions.deleteGraph',
  extractNew: 'projects.state.actions.extractNew',
  rebuild: 'projects.state.actions.rebuild',
  disable: 'projects.state.actions.disable',
  // F2 — dedicated label for the model-change confirm path so the BE
  // error toast reads "Confirm model change: <error>" rather than the
  // generic "Confirm: <error>" from the shared confirm button.
  confirmModelChange: 'projects.state.actions.confirmModelChange',
} as const;

// Exported so ProjectRow can share the same keys for the destructive
// confirm flows it lifts. One canonical source, two consumers.
export const PROJECT_ACTION_KEYS = ACTION_KEYS;

const EMPTY_STATS: GraphStats = {
  entity_count: 0,
  fact_count: 0,
  event_count: 0,
  passage_count: 0,
  last_extracted_at: '',
};

const ACTIVE_STATUSES: ReadonlySet<ExtractionJobStatus> = new Set(['pending', 'running']);

// review-impl F5 — defensive Decimal-string → number. BE ships asyncpg
// Decimal as an ISO-ish numeric string ("5.00"), but fall back to 0 on
// NaN so a misformatted response doesn't cause `NaN >= cap` comparisons
// to silently return false.
function parseDecimal(s: string | null | undefined): number | null {
  if (s == null) return null;
  const n = Number.parseFloat(s);
  return Number.isFinite(n) ? n : null;
}

export function scopeOfJob(wire: ExtractionJobWire): JobScope {
  // BE stores scope as a literal + optional scope_range dict. The UI
  // flattens into a discriminated union: {kind:'chapters', range?} etc.
  const k = wire.scope;
  if (k === 'chapters') {
    const r = wire.scope_range;
    if (
      r &&
      Array.isArray(r.chapter_range) &&
      r.chapter_range.length === 2 &&
      typeof r.chapter_range[0] === 'number' &&
      typeof r.chapter_range[1] === 'number'
    ) {
      return {
        kind: 'chapters',
        range: { from_sort: r.chapter_range[0], to_sort: r.chapter_range[1] },
      };
    }
    return { kind: 'chapters' };
  }
  return { kind: k };
}

function toSummary(wire: ExtractionJobWire): ExtractionJobSummary {
  return {
    job_id: wire.job_id,
    status: wire.status,
    scope: scopeOfJob(wire),
    items_processed: wire.items_processed,
    items_total: wire.items_total,
    cost_spent_usd: wire.cost_spent_usd,
    max_spend_usd: wire.max_spend_usd,
    started_at: wire.started_at,
    error_message: wire.error_message,
  };
}

function toGraphStats(
  wire: GraphStatsResponse | null | undefined,
): GraphStats {
  if (!wire) return EMPTY_STATS;
  return {
    entity_count: wire.entity_count,
    fact_count: wire.fact_count,
    event_count: wire.event_count,
    passage_count: wire.passage_count,
    last_extracted_at: wire.last_extracted_at ?? '',
  };
}

export function deriveState(
  project: Project,
  jobs: readonly ExtractionJobWire[],
  stats: GraphStatsResponse | null,
): ProjectMemoryState {
  if (!project.extraction_enabled) return { kind: 'disabled' };

  const latest = jobs[0];
  if (!latest) {
    // extraction_enabled=true without any job shouldn't happen in
    // steady state; until K19a.5 opens the enable-flip flow, fall
    // back conservatively.
    return { kind: 'disabled' };
  }

  const summary = toSummary(latest);

  switch (latest.status) {
    case 'pending':
    case 'running':
      return { kind: 'building_running', job: summary };

    case 'paused': {
      const spent = parseDecimal(latest.cost_spent_usd) ?? 0;
      const cap = parseDecimal(latest.max_spend_usd);
      if (cap != null && spent >= cap) {
        return {
          kind: 'building_paused_budget',
          job: summary,
          budgetRemaining: Math.max(0, cap - spent),
        };
      }
      if (latest.error_message) {
        return {
          kind: 'building_paused_error',
          job: summary,
          error: latest.error_message,
        };
      }
      return { kind: 'building_paused_user', job: summary };
    }

    case 'complete':
      return { kind: 'complete', stats: toGraphStats(stats) };

    case 'failed':
      return {
        kind: 'failed',
        error: latest.error_message ?? 'unknown error',
        canRetry: true,
      };

    case 'cancelled':
      // KSA §8.4: cancelled jobs revert to disabled (partial graph kept).
      return { kind: 'disabled' };

    default:
      return { kind: 'disabled' };
  }
}

export interface UseProjectStateResult {
  state: ProjectMemoryState;
  actions: ProjectStateCardActions;
  isLoading: boolean;
  error: Error | null;
}

// review-impl F2 — shared wrapper: await the action, surface BE errors as
// toasts, and invalidate both queries on success. K19a.7 — `labelKey` is
// an i18n key (under `projects.state.actions.*`) resolved through the
// parent `t`; the hardcoded English "failed:" template was also moved
// into a `projects.toast.actionFailed` key.
async function runAction(
  // K19a.7 review-impl F3 — canonical i18next v26 tuple form. `useTranslation('knowledge')`
  // returns `TFunction<['knowledge'], undefined>`; the string form widens but the
  // tuple form is what react-i18next actually hands back.
  t: TFunction<['knowledge'], undefined>,
  labelKey: string,
  op: () => Promise<unknown>,
  invalidate: () => void,
): Promise<void> {
  try {
    await op();
    invalidate();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    const label = t(labelKey);
    toast.error(t('projects.toast.actionFailed', { label, error: msg }));
  }
}

export function useProjectState(project: Project): UseProjectStateResult {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const { t } = useTranslation('knowledge');

  const jobsQueryKey = ['knowledge-project-jobs', project.project_id] as const;
  const statsQueryKey = ['knowledge-project-graph-stats', project.project_id] as const;

  const jobsQuery = useQuery({
    queryKey: jobsQueryKey,
    queryFn: () => knowledgeApi.listExtractionJobs(project.project_id, accessToken!),
    enabled: !!accessToken,
    refetchInterval: (query) => {
      const data = query.state.data as ExtractionJobWire[] | undefined;
      const latest = data?.[0];
      if (!latest) return false;
      return ACTIVE_STATUSES.has(latest.status) ? POLL_INTERVAL_MS : false;
    },
  });

  // Only fetch stats when the project has been through an extraction.
  // `extraction_enabled=true` is a sufficient proxy — a disabled project
  // with a live graph is an edge case this hook doesn't need to optimise.
  const statsQuery = useQuery({
    queryKey: statsQueryKey,
    queryFn: () => knowledgeApi.getGraphStats(project.project_id, accessToken!),
    enabled: !!accessToken && project.extraction_enabled,
    staleTime: 10_000,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: jobsQueryKey });
    void queryClient.invalidateQueries({ queryKey: statsQueryKey });
  };

  const state = useMemo(
    () =>
      deriveState(
        project,
        jobsQuery.data ?? [],
        statsQuery.data ?? null,
      ),
    [project, jobsQuery.data, statsQuery.data],
  );

  // review-impl F6 — depend on the latest job's IDENTITY, not the whole
  // data array. Items_processed changes every poll tick during a running
  // job; re-creating the entire actions object then means every
  // ProjectStateCard below re-renders for a change that doesn't affect
  // any callback. Job identity (job_id + model refs) is what we need.
  const latestJob = jobsQuery.data?.[0];
  const latestJobId = latestJob?.job_id ?? null;
  const latestLlmModel = latestJob?.llm_model ?? null;
  const latestEmbeddingModel = latestJob?.embedding_model ?? null;
  const latestScope = latestJob?.scope ?? null;

  const actions = useMemo<ProjectStateCardActions>(() => {
    const token = accessToken;

    // review-impl F1 — /start + /rebuild both require embedding_model.
    // Use the latest job's model refs as replay parameters.
    const replayPayload = (scopeOverride?: ExtractionJobScopeWire) => {
      if (!latestJobId || !latestLlmModel || !latestEmbeddingModel || !latestScope) {
        return null;
      }
      return {
        scope: scopeOverride ?? latestScope,
        llm_model: latestLlmModel,
        embedding_model: latestEmbeddingModel,
      };
    };

    return {
      // K19a.5 + K19a.6 — five dialog/confirm-dependent actions are
      // owned by the parent. ProjectRow lifts dialog state and merges
      // overrides on top of these no-ops. Left as silent no-ops so the
      // hook can return a complete 14-action surface without forcing
      // every caller to know the set; if a future caller forgets to
      // merge, the affected card button will look dead — immediately
      // noticeable in smoke test.
      //
      // K19a.5 owns: onBuildGraph, onStart, onViewError
      // K19a.6 owns: onChangeModel, onDisable
      onBuildGraph: () => {},
      onViewError: () => {},
      onStart: () => {},
      onChangeModel: () => {},
      onDisable: () => {},
      onIgnoreStale: () => {
        // Client-only no-op for MVP. A future version can set a
        // per-session dismissed flag that suppresses the stale UI
        // until new extraction completes.
      },

      onPause: () => {
        if (!token) return;
        void runAction(t, ACTION_KEYS.pause, () => knowledgeApi.pauseExtraction(project.project_id, token), invalidate);
      },
      onResume: () => {
        if (!token) return;
        void runAction(t, ACTION_KEYS.resume, () => knowledgeApi.resumeExtraction(project.project_id, token), invalidate);
      },
      onCancel: () => {
        if (!token) return;
        void runAction(t, ACTION_KEYS.cancel, () => knowledgeApi.cancelExtraction(project.project_id, token), invalidate);
      },
      onDeleteGraph: () => {
        if (!token) return;
        void runAction(t, ACTION_KEYS.deleteGraph, () => knowledgeApi.deleteGraph(project.project_id, token), invalidate);
      },

      onRetry: () => {
        if (!token) return;
        const payload = replayPayload();
        if (!payload) {
          toast.error(t('projects.toast.noPriorJob'));
          return;
        }
        void runAction(t, ACTION_KEYS.retry, () => knowledgeApi.startExtraction(project.project_id, payload, token), invalidate);
      },
      onExtractNew: () => {
        if (!token) return;
        const payload = replayPayload('chapters');
        if (!payload) {
          toast.error(t('projects.toast.noPriorJob'));
          return;
        }
        void runAction(t, ACTION_KEYS.extractNew, () => knowledgeApi.startExtraction(project.project_id, payload, token), invalidate);
      },
      onRebuild: () => {
        if (!token) return;
        if (!latestLlmModel || !latestEmbeddingModel) {
          toast.error(t('projects.toast.noPriorRebuild'));
          return;
        }
        void runAction(
          t,
          ACTION_KEYS.rebuild,
          () =>
            knowledgeApi.rebuildGraph(
              project.project_id,
              { llm_model: latestLlmModel, embedding_model: latestEmbeddingModel },
              token,
            ),
          invalidate,
        );
      },
      onConfirmModelChange: () => {
        if (!token) return;
        if (!latestLlmModel || !latestEmbeddingModel) {
          toast.error(t('projects.toast.noPriorRebuild'));
          return;
        }
        void runAction(
          t,
          ACTION_KEYS.confirmModelChange,
          () =>
            knowledgeApi.rebuildGraph(
              project.project_id,
              { llm_model: latestLlmModel, embedding_model: latestEmbeddingModel },
              token,
            ),
          invalidate,
        );
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    accessToken,
    project.project_id,
    latestJobId,
    latestLlmModel,
    latestEmbeddingModel,
    latestScope,
    // `t` is stable across renders unless language changes; when the
    // user switches language the toast templates should re-bind, so
    // include it in the dep list.
    t,
  ]);

  return {
    state,
    actions,
    isLoading: jobsQuery.isLoading,
    error: (jobsQuery.error ?? statsQuery.error) as Error | null,
  };
}
