import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { toast } from 'sonner';
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
// Scope of THIS cycle: derives every state that can be reached without the
// BuildGraphDialog (K19a.5). That means `disabled`, `building_running`,
// `building_paused_{user,budget,error}`, `complete`, `failed`. `cancelling`,
// `deleting`, `model_change_pending`, `stale` are all deferred — signals
// not yet plumbed. `estimating` / `ready_to_build` are produced by the
// dialog itself when it lands.
//
// Callbacks: 11 real, 3 stubs. The stubs show a toast instead of firing an
// API call. All real actions are wrapped in try/catch + toast.error so BE
// failures surface visibly (review-impl F2).

const POLL_INTERVAL_MS = 2000;

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
// toasts, and invalidate both queries on success.
async function runAction(
  label: string,
  op: () => Promise<unknown>,
  invalidate: () => void,
): Promise<void> {
  try {
    await op();
    invalidate();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    toast.error(`${label} failed: ${msg}`);
  }
}

export function useProjectState(project: Project): UseProjectStateResult {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

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
      onBuildGraph: () => {
        toast.info('Build graph dialog lands in K19a.5.');
      },
      onViewError: () => {
        toast.info('Error viewer lands in K19a.5.');
      },
      onChangeModel: () => {
        toast.info('Change model dialog lands in K19a.6.');
      },
      onDisable: () => {
        toast.info('Disable-without-delete lands in K19a.6; use Delete graph for now.');
      },
      onStart: () => {
        toast.info('Start requires the Build dialog (K19a.5) to pick LLM model.');
      },
      onIgnoreStale: () => {
        // Client-only no-op for MVP. A future version can set a
        // per-session dismissed flag that suppresses the stale UI
        // until new extraction completes.
      },

      onPause: () => {
        if (!token) return;
        void runAction('Pause', () => knowledgeApi.pauseExtraction(project.project_id, token), invalidate);
      },
      onResume: () => {
        if (!token) return;
        void runAction('Resume', () => knowledgeApi.resumeExtraction(project.project_id, token), invalidate);
      },
      onCancel: () => {
        if (!token) return;
        void runAction('Cancel', () => knowledgeApi.cancelExtraction(project.project_id, token), invalidate);
      },
      onDeleteGraph: () => {
        if (!token) return;
        void runAction('Delete graph', () => knowledgeApi.deleteGraph(project.project_id, token), invalidate);
      },

      onRetry: () => {
        if (!token) return;
        const payload = replayPayload();
        if (!payload) {
          toast.error('No previous job to replay — open the Build dialog.');
          return;
        }
        void runAction('Retry', () => knowledgeApi.startExtraction(project.project_id, payload, token), invalidate);
      },
      onExtractNew: () => {
        if (!token) return;
        const payload = replayPayload('chapters');
        if (!payload) {
          toast.error('No previous job to replay — open the Build dialog.');
          return;
        }
        void runAction('Extract new', () => knowledgeApi.startExtraction(project.project_id, payload, token), invalidate);
      },
      onRebuild: () => {
        if (!token) return;
        if (!latestLlmModel || !latestEmbeddingModel) {
          toast.error('No previous job to rebuild from.');
          return;
        }
        void runAction(
          'Rebuild',
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
          toast.error('No previous job to rebuild from.');
          return;
        }
        void runAction(
          'Confirm model change',
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
  ]);

  return {
    state,
    actions,
    isLoading: jobsQuery.isLoading,
    error: (jobsQuery.error ?? statsQuery.error) as Error | null,
  };
}
