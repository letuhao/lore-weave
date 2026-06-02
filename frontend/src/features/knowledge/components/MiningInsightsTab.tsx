import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';
import type {
  MiningConfigQualityResponse,
  MiningModelMatrixResponse,
  MiningDefaultDriftResponse,
  MiningOutcomeRecomputeResponse,
} from '../api';

const pct = (v: number | null): string =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`;

// ── Shared shell ──────────────────────────────────────────────────────────

function SectionShell({
  title,
  description,
  children,
  collapsedByDefault,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  collapsedByDefault?: boolean;
}) {
  return (
    <details
      open={!collapsedByDefault}
      className="group rounded-lg border bg-card"
    >
      <summary className="cursor-pointer select-none px-4 py-3 text-[13px] font-medium">
        <span className="mr-2 inline-block w-3 text-muted-foreground transition-transform group-open:rotate-90">
          ▸
        </span>
        {title}
      </summary>
      <div className="border-t px-4 py-3">
        <p className="mb-3 text-[12px] text-muted-foreground">{description}</p>
        {children}
      </div>
    </details>
  );
}

function Empty({ msg }: { msg: string }) {
  return <p className="text-[12px] text-muted-foreground">{msg}</p>;
}

function LoadRow() {
  const { t } = useTranslation('knowledge');
  return (
    <p className="text-[12px] text-muted-foreground">
      {t('global.loading', { defaultValue: 'Loading…' })}
    </p>
  );
}

// ── Config Quality ────────────────────────────────────────────────────────

function QualityTable({ rows }: { rows: MiningConfigQualityResponse['items'] }) {
  const { t } = useTranslation('knowledge');
  return (
    <table className="w-full text-[12px]" data-testid="config-quality-table">
      <thead>
        <tr className="text-left text-[11px] text-muted-foreground">
          <th className="pb-1 pr-4 font-medium">{t('mining.columns.genre')}</th>
          <th className="pb-1 pr-4 font-medium">{t('mining.columns.configHash')}</th>
          <th className="pb-1 pr-4 text-right font-medium">{t('mining.columns.runs')}</th>
          <th className="pb-1 pr-4 text-right font-medium">{t('mining.columns.successRate')}</th>
          <th className="pb-1 text-right font-medium">{t('mining.columns.avgEntities')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.config_hash + (r.genre ?? '')} className="border-t border-border/50">
            <td className="py-1 pr-4">{r.genre ?? '—'}</td>
            <td className="py-1 pr-4 font-mono text-[11px]" title={r.config_hash}>
              {r.config_hash.slice(0, 8)}
            </td>
            <td className="py-1 pr-4 text-right">{r.run_count}</td>
            <td className="py-1 pr-4 text-right">{pct(r.success_rate)}</td>
            <td className="py-1 text-right">{r.avg_entities_on_success?.toFixed(1) ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ConfigQualitySection({ token }: { token: string }) {
  const { t } = useTranslation('knowledge');
  const { data, isLoading, error } = useQuery({
    queryKey: ['learning-mining-config-quality'] as const,
    queryFn: () => knowledgeApi.miningConfigQuality(token),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <SectionShell
      title={t('mining.sections.configQuality.title')}
      description={t('mining.sections.configQuality.description')}
    >
      {isLoading && <LoadRow />}
      {error && (
        <p className="text-[12px] text-destructive">{(error as Error).message}</p>
      )}
      {data && data.items.length === 0 && (
        <Empty msg={t('mining.sections.configQuality.empty')} />
      )}
      {data && data.items.length > 0 && <QualityTable rows={data.items} />}
      {data && data.exploration.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">
            {t('mining.sections.configQuality.exploration')}
          </p>
          <QualityTable rows={data.exploration} />
        </div>
      )}
    </SectionShell>
  );
}

// ── Model Matrix ──────────────────────────────────────────────────────────

function ModelMatrixSection({ token }: { token: string }) {
  const { t } = useTranslation('knowledge');
  const { data, isLoading, error } = useQuery({
    queryKey: ['learning-mining-model-matrix'] as const,
    queryFn: () => knowledgeApi.miningModelMatrix(token),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <SectionShell
      title={t('mining.sections.modelMatrix.title')}
      description={t('mining.sections.modelMatrix.description')}
      collapsedByDefault
    >
      {isLoading && <LoadRow />}
      {error && (
        <p className="text-[12px] text-destructive">{(error as Error).message}</p>
      )}
      {data && data.items.length === 0 && (
        <Empty msg={t('mining.sections.modelMatrix.empty')} />
      )}
      {data && data.items.length > 0 && (
        <table className="w-full text-[12px]" data-testid="model-matrix-table">
          <thead>
            <tr className="text-left text-[11px] text-muted-foreground">
              <th className="pb-1 pr-4 font-medium">{t('mining.columns.model')}</th>
              <th className="pb-1 pr-4 font-medium">{t('mining.columns.scope')}</th>
              <th className="pb-1 pr-4 font-medium">{t('mining.columns.filter')}</th>
              <th className="pb-1 pr-4 text-right font-medium">{t('mining.columns.runs')}</th>
              <th className="pb-1 text-right font-medium">{t('mining.columns.weightedOutcome')}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r, i) => (
              <tr key={i} className="border-t border-border/50">
                <td
                  className="max-w-[160px] truncate py-1 pr-4 font-mono text-[11px]"
                  title={r.model_ref ?? ''}
                >
                  {r.model_ref ?? '—'}
                </td>
                <td className="py-1 pr-4">{r.scope ?? '—'}</td>
                <td className="py-1 pr-4">{r.has_filter ? '✓' : '—'}</td>
                <td className="py-1 pr-4 text-right">{r.run_count}</td>
                <td className="py-1 text-right">{pct(r.weighted_outcome)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </SectionShell>
  );
}

// ── Config Drift ──────────────────────────────────────────────────────────

function DefaultDriftSection({ token }: { token: string }) {
  const { t } = useTranslation('knowledge');
  const { data, isLoading, error } = useQuery({
    queryKey: ['learning-mining-default-drift'] as const,
    queryFn: () => knowledgeApi.miningDefaultDrift(token),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <SectionShell
      title={t('mining.sections.defaultDrift.title')}
      description={t('mining.sections.defaultDrift.description')}
      collapsedByDefault
    >
      {isLoading && <LoadRow />}
      {error && (
        <p className="text-[12px] text-destructive">{(error as Error).message}</p>
      )}
      {data && data.items.length === 0 && (
        <Empty msg={t('mining.sections.defaultDrift.empty')} />
      )}
      {data && data.items.length > 0 && (
        <table className="w-full text-[12px]" data-testid="default-drift-table">
          <thead>
            <tr className="text-left text-[11px] text-muted-foreground">
              <th className="pb-1 pr-4 font-medium">{t('mining.columns.target')}</th>
              <th className="pb-1 pr-4 text-right font-medium">{t('mining.columns.affectedProjects')}</th>
              <th className="pb-1 pr-4 font-medium">{t('mining.columns.driftPattern')}</th>
              <th className="pb-1 text-right font-medium">{t('mining.columns.runsWithOutcome')}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r, i) => (
              <tr key={i} className="border-t border-border/50">
                <td className="py-1 pr-4 font-mono text-[11px]">{r.target}</td>
                <td className="py-1 pr-4 text-right">{r.affected_projects}</td>
                <td className="py-1 pr-4">
                  <span
                    className={
                      r.drift_pattern === 'convergent'
                        ? 'rounded bg-green-100 px-1.5 py-0.5 text-[11px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : 'rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                    }
                  >
                    {t(`mining.driftPattern.${r.drift_pattern}`, {
                      defaultValue: r.drift_pattern,
                    })}
                  </span>
                </td>
                <td className="py-1 text-right">{r.runs_with_outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </SectionShell>
  );
}

// ── Outcome Recompute ─────────────────────────────────────────────────────

function OutcomeRecomputeSection({ token }: { token: string }) {
  const { t } = useTranslation('knowledge');
  const { data, isLoading, error } = useQuery({
    queryKey: ['learning-mining-outcome-recompute'] as const,
    queryFn: () => knowledgeApi.miningOutcomeRecompute(token),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <SectionShell
      title={t('mining.sections.outcomeRecompute.title')}
      description={t('mining.sections.outcomeRecompute.description')}
      collapsedByDefault
    >
      {isLoading && <LoadRow />}
      {error && (
        <p className="text-[12px] text-destructive">{(error as Error).message}</p>
      )}
      {data && data.items.length === 0 && (
        <Empty msg={t('mining.sections.outcomeRecompute.empty')} />
      )}
      {data && data.items.length > 0 && (
        <>
          <p className="mb-2 text-[11px] text-muted-foreground">
            {t('mining.totalRuns', { count: data.total, defaultValue: `${data.total} runs total` })}
          </p>
          <table className="w-full text-[12px]" data-testid="outcome-recompute-table">
            <thead>
              <tr className="text-left text-[11px] text-muted-foreground">
                <th className="pb-1 pr-4 font-medium">{t('mining.columns.runId')}</th>
                <th className="pb-1 pr-4 font-medium">{t('mining.columns.outcome')}</th>
                <th className="pb-1 pr-4 font-medium">{t('mining.columns.recomputed')}</th>
                <th className="pb-1 text-right font-medium">{t('mining.columns.corrections')}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={String(r.run_id)} className="border-t border-border/50">
                  <td className="py-1 pr-4 font-mono text-[11px]">
                    {String(r.run_id).slice(0, 8)}
                  </td>
                  <td className="py-1 pr-4">{r.pipeline_outcome ?? '—'}</td>
                  <td className="py-1 pr-4">{r.recomputed_outcome ?? '—'}</td>
                  <td className="py-1 text-right">{r.post_run_corrections}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </SectionShell>
  );
}

// ── Tab root ──────────────────────────────────────────────────────────────

export function MiningInsightsTab() {
  const { accessToken } = useAuth();
  if (!accessToken) return null;

  return (
    <div className="space-y-3">
      <ConfigQualitySection token={accessToken} />
      <ModelMatrixSection token={accessToken} />
      <DefaultDriftSection token={accessToken} />
      <OutcomeRecomputeSection token={accessToken} />
    </div>
  );
}
