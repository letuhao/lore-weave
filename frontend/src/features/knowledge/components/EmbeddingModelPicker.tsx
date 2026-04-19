import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';
import { knowledgeApi } from '../api';
import type { BenchmarkStatus } from '../types';

/**
 * K12.4 — Embedding model picker for knowledge projects.
 *
 * Fetches the user's BYOK models tagged `capability=embedding` from
 * provider-registry and renders a `<select>` bound to the caller's
 * state. Selecting `""` clears the project's embedding_model
 * (backend treats null as "no L3 for this project").
 *
 * Why this lives in the knowledge feature rather than ai-models:
 * ai-models is the registry management page (add/remove/edit
 * credentials); knowledge/ is the consumer-side that picks WHICH
 * registered model this project uses. The picker is a small view
 * wrapper; the actual model list API stays in ai-models/api.ts.
 *
 * T2-close-1b-FE: when `projectId` + a selected model are both
 * present, the picker renders a K17.9 benchmark-status badge
 * (passed / failed / no-run-yet) so users see quality signal
 * BEFORE they attempt to enable extraction and hit a 409 from the
 * backend gate.
 */
interface Props {
  value: string | null;
  onChange: (modelName: string | null) => void;
  disabled?: boolean;
  /** Enables the K17.9 benchmark-status badge. Omit in create
   * flows (no project yet) — the badge simply doesn't render. */
  projectId?: string;
}

export function EmbeddingModelPicker({ value, onChange, disabled, projectId }: Props) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const [models, setModels] = useState<UserModel[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!accessToken) {
      setModels([]);
      return;
    }
    let cancelled = false;
    setError(null);
    aiModelsApi
      .listUserModels(accessToken, { capability: 'embedding', include_inactive: false })
      .then((resp) => {
        if (cancelled) return;
        setModels(resp.items);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const loading = models === null;
  // Guard: if the project's current `value` doesn't appear in the
  // fetched models (model deleted from registry, server-side fallback
  // name, etc.) the <select> would render no matching <option> and
  // the browser would silently show "None" — misrepresenting the
  // real state. Detect and surface a synthetic option so the user
  // sees the truth.
  const valueInOptions =
    value === null ||
    (models?.some((m) => m.provider_model_name === value) ?? false);

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.form.embeddingModel', {
          defaultValue: 'Embedding model',
        })}
      </span>
      <select
        value={value ?? ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === '' ? null : v);
        }}
        disabled={disabled || loading}
        className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
      >
        <option value="">
          {t('projects.form.embeddingModelNone', {
            defaultValue: 'None (no semantic passages)',
          })}
        </option>
        {!valueInOptions && value !== null && (
          <option value={value}>
            {t('projects.form.embeddingModelOrphan', {
              defaultValue: '{{name}} (not in your registry)',
              name: value,
            })}
          </option>
        )}
        {(models ?? []).map((m) => {
          const label = m.alias
            ? `${m.alias} (${m.provider_model_name})`
            : `${m.provider_kind}/${m.provider_model_name}`;
          return (
            <option key={m.user_model_id} value={m.provider_model_name}>
              {label}
            </option>
          );
        })}
      </select>
      {loading && (
        <span className="text-[11px] text-muted-foreground">
          {t('projects.form.embeddingModelLoading', {
            defaultValue: 'Loading embedding models…',
          })}
        </span>
      )}
      {error && (
        <span className="text-[11px] text-destructive">
          {t('projects.form.embeddingModelError', {
            defaultValue: 'Failed to load embedding models.',
          })}
        </span>
      )}
      {!loading && !error && accessToken && (models?.length ?? 0) === 0 && (
        // Only show "registry empty" when we actually attempted to load
        // with a valid token. Without this gate, an unauthed render
        // (hypothetical — route guards normally prevent it) would
        // falsely tell the user to add a model.
        <span className="text-[11px] text-muted-foreground">
          {t('projects.form.embeddingModelEmpty', {
            defaultValue:
              'No embedding-capable models configured. Add one in AI Models → Credentials.',
          })}
        </span>
      )}
      <span className="text-[11px] text-muted-foreground">
        {t('projects.form.embeddingModelHint', {
          defaultValue:
            'Governs which vector space this project uses for semantic passage retrieval.',
        })}
      </span>
      {projectId && value && benchmarkQuery.data && (
        <BenchmarkBadge status={benchmarkQuery.data} />
      )}
    </label>
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
  return (
    <span className="text-[11px] text-destructive">
      {t('projects.form.benchmarkFailed', {
        defaultValue:
          '✗ Benchmark failed (recall@3 {{recall}}) — extraction would produce low-quality results.',
        recall: status.recall_at_3?.toFixed(2) ?? '—',
      })}
    </span>
  );
}
