import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Loader2, CheckCircle2, MessageSquarePlus, CircleSlash, XCircle,
  ChevronDown, ChevronRight, X, Link2, AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WikiGenJobStatus, WikiEntityResult } from '../types';

/**
 * wiki-llm W4b — the screen-③ per-entity results table + live pass indicator.
 *
 * Reads W4a's `results` (entity_id → outcome/citations/flags/name) + the live
 * `current_pass` off the polled job (which flows through the verbatim glossary
 * proxy). A separate component from the banner because it must persist AFTER the
 * run (the banner hides on complete): a collapsible panel that auto-expands while
 * the job is active and auto-collapses on completion (`open ?? isActive`), with a
 * user toggle that sticks + a dismiss. Reset per job via a `key={job_id}` parent.
 */

const PASS_ORDER = ['context', 'generate', 'verify', 'revise', 'writeback'] as const;

/** Rank for the row sort — the live 'processing' row first, then by terminal state. */
function rank(outcome: string): number {
  switch (outcome) {
    case 'processing': return 0;
    case 'written': return 1;
    case 'suggestion': return 2;
    case 'skipped': return 3;
    default: return 4; // writeback_failed | error | unknown
  }
}

function OutcomeIcon({ outcome }: { outcome: string }) {
  switch (outcome) {
    case 'processing': return <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />;
    case 'written': return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />;
    case 'suggestion': return <MessageSquarePlus className="h-3.5 w-3.5 shrink-0 text-primary" />;
    case 'skipped': return <CircleSlash className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
    default: return <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />;
  }
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

function ResultRow({ entityId, r, isLive, pass, t }: {
  entityId: string;
  r: WikiEntityResult;
  isLive: boolean;
  pass: string | null | undefined;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const passIdx = pass ? PASS_ORDER.indexOf(pass as (typeof PASS_ORDER)[number]) + 1 : 0;
  return (
    <div
      data-testid="wiki-gen-detail-row"
      className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-[11px] last:border-b-0"
    >
      <OutcomeIcon outcome={r.outcome} />
      <span className="min-w-0 flex-1 truncate" title={r.name || entityId}>
        {r.name || shortId(entityId)}
      </span>
      {isLive && r.outcome === 'processing' ? (
        <span data-testid="wiki-gen-detail-pass" className="shrink-0 text-primary">
          {t(`gen.pass.${pass}`)}{passIdx > 0 && ` (${passIdx}/${PASS_ORDER.length})`}
        </span>
      ) : (
        <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
          <span className="text-[10px]">{t(`gen.outcome.${r.outcome}`)}</span>
          {r.citations > 0 && (
            <span className="inline-flex items-center gap-0.5" title={t('gen.results.cites')}>
              <Link2 className="h-3 w-3" />{r.citations}
            </span>
          )}
          {r.flags > 0 && (
            <span className="inline-flex items-center gap-0.5 text-amber-500" title={t('gen.results.flags')}>
              <AlertTriangle className="h-3 w-3" />{r.flags}
            </span>
          )}
        </span>
      )}
    </div>
  );
}

export function WikiGenJobDetail({ job }: { job: WikiGenJobStatus | null }) {
  const { t } = useTranslation('wiki');
  const [open, setOpen] = useState<boolean | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const resultsObj = job?.results;
  const rows = useMemo(() => {
    const entries = Object.entries(resultsObj ?? {});
    return entries.sort((a, b) => rank(a[1].outcome) - rank(b[1].outcome));
  }, [resultsObj]);

  const counts = useMemo(() => {
    const c = { done: 0, suggestion: 0, skipped: 0, failed: 0, processing: 0 };
    for (const r of Object.values(resultsObj ?? {})) {
      if (r.outcome === 'written') c.done++;
      else if (r.outcome === 'suggestion') c.suggestion++;
      else if (r.outcome === 'processing') c.processing++;
      else if (r.outcome === 'writeback_failed' || r.outcome === 'error') c.failed++;
      else c.skipped++;
    }
    return c;
  }, [resultsObj]);

  if (!job || rows.length === 0 || dismissed) return null;

  const isActive = job.status === 'pending' || job.status === 'running';
  const expanded = open ?? isActive;
  const queued = Math.max(0, job.entity_count - rows.length);

  return (
    <div className="mb-3 rounded-lg border bg-card" data-testid="wiki-gen-detail">
      {/* Header — always visible; click toggles the table. */}
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen(!expanded)}
          aria-expanded={expanded}
          data-testid="wiki-gen-detail-toggle"
          className="inline-flex items-center gap-1 text-xs font-medium hover:text-primary"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {t('gen.results.title')}
        </button>
        <div className="ml-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[10px] text-muted-foreground">
          {counts.processing > 0 && (
            <span className="inline-flex items-center gap-0.5 text-primary">
              <Loader2 className="h-2.5 w-2.5 animate-spin" />{counts.processing}
            </span>
          )}
          {counts.done > 0 && <span className="text-emerald-500">{t('gen.outcome.written')} {counts.done}</span>}
          {counts.suggestion > 0 && <span>{t('gen.outcome.suggestion')} {counts.suggestion}</span>}
          {counts.skipped > 0 && <span>{t('gen.outcome.skipped')} {counts.skipped}</span>}
          {counts.failed > 0 && <span className="text-destructive">{t('gen.outcome.error')} {counts.failed}</span>}
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label={t('gen.results.dismiss')}
          data-testid="wiki-gen-detail-dismiss"
          className="ml-auto shrink-0 rounded p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Table — per-entity rows, processing first. */}
      {expanded && (
        <div className="border-t">
          {rows.map(([entityId, r]) => (
            <ResultRow
              key={entityId}
              entityId={entityId}
              r={r}
              isLive={entityId === job.current_entity_id}
              pass={job.current_pass}
              t={t}
            />
          ))}
          {queued > 0 && (
            <div className="px-3 py-1.5 text-[10px] text-muted-foreground">
              {t('gen.results.queued', { count: queued })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
