import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { AddModelCta } from '@/components/shared/AddModelCta';
import { ModelPicker } from '@/components/model-picker';
import { knowledgeApi } from '../api';
import {
  useRunBenchmark,
  type RunBenchmarkErrorCode,
} from '../hooks/useRunBenchmark';
import type { BenchmarkStatus } from '../types';

/**
 * K12.4 — Embedding model picker for knowledge projects.
 *
 * W5: now a THIN WRAPPER around the shared {@link ModelPicker}
 * (`capability="embedding"`) — the bespoke fetch effect + orphan-option
 * logic moved into the shared component. This wrapper keeps the
 * site-specific label / hint / empty-state copy and the K17.9
 * benchmark-status badge + Run-benchmark CTA.
 *
 * The bound value is the model's `user_model_id` UUID — the provider
 * `model_ref` the backend embeds with (D-EMB-MODEL-REF-03; the backend
 * probes the UUID to derive `embedding_dimension`). Selecting the
 * "None" option clears the project's embedding model (backend treats
 * null as "no L3 for this project").
 *
 * Why this lives in the knowledge feature rather than ai-models:
 * ai-models is the registry management page (add/remove/edit
 * credentials); knowledge/ is the consumer-side that picks WHICH
 * registered model this project uses.
 *
 * T2-close-1b-FE: when `projectId` + a selected model are both
 * present, the picker renders a K17.9 benchmark-status badge
 * (passed / failed / no-run-yet) so users see quality signal
 * BEFORE they attempt to enable extraction and hit a 409 from the
 * backend gate.
 */
interface Props {
  /** The selected embedding model's `user_model_id` UUID, or null. */
  value: string | null;
  onChange: (userModelId: string | null) => void;
  disabled?: boolean;
  /** Enables the K17.9 benchmark-status badge. Omit in create
   * flows (no project yet) — the badge simply doesn't render. */
  projectId?: string;
}

export function EmbeddingModelPicker({ value, onChange, disabled, projectId }: Props) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();

  // T2-close-1b-FE — benchmark-status badge. Only fires when the
  // caller passes a projectId AND a model is selected. Stale-for-60s
  // is fine: benchmarks run at human cadence (one per model switch).
  const benchmarkQuery = useQuery({
    queryKey: ['knowledge', 'benchmark-status', projectId, value],
    queryFn: () =>
      knowledgeApi.getBenchmarkStatus(projectId!, value, accessToken!),
    enabled: !!projectId && !!value && !!accessToken,
    staleTime: 60_000,
    // A 404 (cross-user / nonexistent project) shouldn't alarm —
    // degrade silently by not rendering the badge.
    retry: false,
  });

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.form.embeddingModel', {
          defaultValue: 'Embedding model',
        })}
      </span>
      <ModelPicker
        capability="embedding"
        value={value}
        onChange={onChange}
        disabled={disabled}
        allowNone
        noneLabel={t('projects.form.embeddingModelNone', {
          defaultValue: 'None (no semantic passages)',
        })}
        ariaLabel={t('projects.form.embeddingModel', {
          defaultValue: 'Embedding model',
        })}
        emptyState={
          // C5 (KN-1/BL-16): embedding is the real build-graph precondition — when
          // none is configured, offer the in-flow AddModelCta (deep-link + return)
          // instead of a dead-end "go to settings" sentence.
          <span className="flex flex-col gap-1 text-[11px] text-muted-foreground">
            {t('projects.form.embeddingModelEmpty', {
              defaultValue:
                'No embedding-capable models configured — extraction needs one.',
            })}
            <AddModelCta capability="embedding" variant="link" />
          </span>
        }
      />
      <span className="text-[11px] text-muted-foreground">
        {t('projects.form.embeddingModelHint', {
          defaultValue:
            'Governs which vector space this project uses for semantic passage retrieval.',
        })}
      </span>
      {projectId && value && benchmarkQuery.data && (
        <>
          <BenchmarkBadge status={benchmarkQuery.data} />
          {/* C12b-b — Run-benchmark CTA. Hidden when `passed=true`
              (no reason to re-run); visible when has_run=false OR
              passed=false (either "Run" or "Re-run"). */}
          {!benchmarkQuery.data.passed && (
            <RunBenchmarkButton projectId={projectId} />
          )}
        </>
      )}
    </div>
  );
}


function BenchmarkBadge({ status }: { status: BenchmarkStatus }) {
  const { t } = useTranslation('knowledge');
  // Three states map to three colors + copy. Keep it inline + tiny —
  // this is a secondary signal the user glances at, not a full
  // report. The "See report" link is Track 3 K19b work.
  if (!status.has_run) {
    return (
      <span className="text-[11px] text-muted-foreground">
        {t('projects.form.benchmarkNoRun', {
          defaultValue:
            '⋯ No benchmark yet — run the golden-set benchmark to enable extraction.',
        })}
      </span>
    );
  }
  if (status.passed) {
    return (
      <span className="text-[11px] text-green-600 dark:text-green-400">
        {t('projects.form.benchmarkPassed', {
          defaultValue:
            '✓ Benchmark passed (recall@3 {{recall}}).',
          recall: status.recall_at_3?.toFixed(2) ?? '—',
        })}
      </span>
    );
  }
  // Not passed. Distinguish "inconclusive" (too few passes — NOT a model-quality
  // problem; recall@3 may be perfect) from a genuine metric failure. R2: never
  // claim "low-quality" when the only failing gate is insufficient_runs.
  const gates = status.gate_failures ?? [];
  const inconclusiveOnly =
    gates.length > 0 && gates.every((g) => g === 'insufficient_runs');
  if (inconclusiveOnly) {
    return (
      <span className="text-[11px] text-amber-600 dark:text-amber-400">
        {t('projects.form.benchmarkInconclusive', {
          defaultValue:
            '⋯ Benchmark inconclusive (recall@3 {{recall}}) — needs ≥3 passes to validate this model. Re-run it.',
          recall: status.recall_at_3?.toFixed(2) ?? '—',
        })}
      </span>
    );
  }
  return (
    <span className="text-[11px] text-destructive">
      {t('projects.form.benchmarkFailed', {
        defaultValue:
          '✗ Benchmark not passing (recall@3 {{recall}}) — this model scored below the quality bar for extraction; try a different embedding model.',
        recall: status.recall_at_3?.toFixed(2) ?? '—',
      })}
    </span>
  );
}


/**
 * C12b-b — Run-benchmark CTA. Inline button under the badge that
 * fires POST /benchmark-run synchronously (15-60s). Disabled with a
 * "Running benchmark…" label while pending; on success, invalidates
 * the benchmark-status query so the sibling badge flips to the fresh
 * pass/fail result.
 *
 * The parent picker hides this when `projectId` / `value` are unset,
 * and when the current badge is already `passed=true`. We still guard
 * with an explicit `projectId` check because the hook defensively
 * throws on undefined.
 *
 * /review-impl notes (accepted findings):
 *   - COSMETIC #6: rapid double-click race is blocked by the
 *     `disabled={mutation.isPending}` attribute being updated
 *     synchronously within React's event tick. Backend sentinel
 *     (`benchmark_already_running` 409) is the belt-and-suspenders
 *     catch for any accidental second submit.
 */
function RunBenchmarkButton({ projectId }: { projectId: string }) {
  const { t } = useTranslation('knowledge');
  const mutation = useRunBenchmark(projectId, {
    onSuccess: (resp) => {
      // review-impl MED #1: the user can change the picker's selected
      // value mid-run (15-60s wait). The toast resolves for the model
      // the BE scored against (resp.embedding_model), which may no
      // longer match the currently-displayed selection. Naming the
      // model in the toast self-discloses scope; without it the user
      // could read "recall 0.82" as describing their current pick
      // rather than the one they had selected at POST time.
      toast.success(
        t('projects.form.benchmark.success', {
          defaultValue:
            'Benchmark complete for {{model}} (recall@3 {{recall}}).',
          model: resp.embedding_model,
          recall: resp.recall_at_3.toFixed(2),
        }),
      );
    },
    onError: (err) => {
      toast.error(runBenchmarkErrorMessage(t, err.errorCode, err.detailMessage));
    },
  });

  return (
    <button
      type="button"
      onClick={() => mutation.mutate({ runs: 3 })}
      disabled={mutation.isPending}
      className="self-start rounded-md border border-primary/40 bg-primary/5 px-2 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {mutation.isPending
        ? t('projects.form.benchmark.running', {
            defaultValue: 'Running benchmark…',
          })
        : t('projects.form.benchmark.run', {
            defaultValue: 'Run benchmark',
          })}
    </button>
  );
}

/**
 * Map a typed error_code from the C12b-a BE into a localised toast
 * message. Keeps the switch here (not in the hook) so the hook stays
 * UI-free and the translation closure is rebuilt per-render with the
 * current locale.
 */
function runBenchmarkErrorMessage(
  t: TFunction<'knowledge'>,
  code: RunBenchmarkErrorCode,
  detailMessage: string | undefined,
): string {
  switch (code) {
    case 'no_embedding_model':
      return t('projects.form.benchmark.errorNoModel', {
        defaultValue:
          'Pick an embedding model before running the benchmark.',
      });
    case 'unknown_embedding_model':
      return t('projects.form.benchmark.errorUnknownModel', {
        defaultValue:
          'This embedding model isn’t supported by the benchmark harness.',
      });
    case 'not_benchmark_project':
      // R1: benchmarks now run automatically on a hidden per-model sandbox, so
      // this is effectively unreachable from the Run-benchmark button; keep a
      // neutral retry message rather than the old (now-wrong) "make a new project".
      return t('projects.form.benchmark.errorNotBenchmarkProject', {
        defaultValue:
          'The benchmark couldn’t start on its sandbox — please retry in a moment.',
      });
    case 'benchmark_already_running':
      return t('projects.form.benchmark.errorAlreadyRunning', {
        defaultValue:
          'A benchmark is already running for this project. Wait and retry.',
      });
    case 'embedding_provider_flake':
      return t('projects.form.benchmark.errorProviderFlake', {
        defaultValue:
          'Embedding provider failed mid-run. Please retry.',
      });
    default:
      return t('projects.form.benchmark.errorGeneric', {
        defaultValue: 'Benchmark failed: {{message}}',
        message: detailMessage ?? 'unknown error',
      });
  }
}
