import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Inbox, BookText, FileText, Sparkles, ChevronRight, Loader2, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useProposalsInbox } from '../hooks/useProposalsInbox';
import type { ProposalInboxRow, ProposalOrigin, ProposalSourceResult } from '../lib/proposalsInbox';

// C11 (C11-proposals-inbox) — the Pending Proposals inbox tab, rendered inside
// the C6 project-detail shell scoped by ROUTE (G6 — the shell resolves the
// project's book_id and passes it; no project select-box here).
//
// INTEGRATE, don't duplicate (LOCKED): this is a READ-ONLY aggregation of the
// 3 EXISTING review queues (glossary AI drafts · wiki suggestions ·
// lore-enrichment proposals). Every row DEEP-LINKS to that source's OWN review
// UI — no in-row mutation controls here; the curation action happens in each
// source's surface. Per-source graceful degrade lives in fetchProposalInbox;
// this view shows an error chip for a down source while still rendering the
// healthy ones.
//
// 14_kg_panels.md K9/DOCK-7 — the row action used to be a raw <Link
// to={row.deepLinkUrl}>, which hard-codes react-router navigation and can't
// be reused from inside a dock panel (DOCK-7 forbids <Link>/useNavigate in a
// panel). Same extraction shape as ProjectsBrowser/ProjectsTab (14_kg_panels.md
// A2): the tab takes an `onOpenRow` callback instead, so the classic
// ProjectDetailShell route can supply `navigate(row.deepLinkUrl)` and the
// studio `kg-proposals` panel can supply `followStudioLink(...)`.

interface ProposalsInboxTabProps {
  // The route-scoped project's book_id (the 3 sources are all book-scoped).
  // null when the project has no linked book → noBook empty-state.
  bookId: string | null;
  // Row click handler — the caller decides how to reach the source's own
  // review UI (route navigate() for the classic shell, the studio link
  // resolver for the `kg-proposals` dock panel). Called with the row's
  // `deepLinkUrl` intact so the caller can pattern-match or navigate as-is.
  onOpenRow: (row: ProposalInboxRow) => void;
}

// Stable origin order so the grouped list is deterministic.
const ORIGIN_ORDER: ProposalOrigin[] = ['glossary', 'wiki', 'enrichment'];

const ORIGIN_ICON: Record<ProposalOrigin, React.ComponentType<{ className?: string }>> = {
  glossary: BookText,
  wiki: FileText,
  enrichment: Sparkles,
};

export function ProposalsInboxTab({ bookId, onOpenRow }: ProposalsInboxTabProps) {
  const { t } = useTranslation('knowledge');
  const { inbox, isLoading, isFetching, error } = useProposalsInbox(bookId);

  // Group the merged rows by origin, in the fixed ORIGIN_ORDER, pairing each
  // group with its source result (so we can render a per-source error chip
  // even when that source returned zero rows).
  const groups = useMemo(() => {
    const bySource = new Map<ProposalOrigin, ProposalSourceResult>();
    for (const s of inbox?.sources ?? []) bySource.set(s.origin, s);
    return ORIGIN_ORDER.map((origin) => ({
      origin,
      source: bySource.get(origin) ?? null,
      rows: (inbox?.rows ?? []).filter((r) => r.origin === origin),
    }));
  }, [inbox]);

  const totalRows = inbox?.rows.length ?? 0;

  return (
    <div data-testid="proposals-inbox-tab" className="space-y-5">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <Inbox className="h-4 w-4 text-primary" />
          <h2 className="font-serif text-base font-semibold">
            {t('proposals.heading')}
          </h2>
          {isFetching && (
            <Loader2
              className="h-3.5 w-3.5 animate-spin text-muted-foreground"
              data-testid="proposals-fetching"
            />
          )}
        </div>
        <p className="text-[12px] text-muted-foreground">
          {t('proposals.subtitle')}
        </p>
      </header>

      {!bookId ? (
        <div
          className="rounded-md border border-dashed p-8 text-center text-[13px] text-muted-foreground"
          data-testid="proposals-no-book"
        >
          {t('proposals.noBook')}
        </div>
      ) : isLoading ? (
        <div
          className="p-6 text-center text-[13px] text-muted-foreground"
          data-testid="proposals-loading"
        >
          {t('proposals.loading')}
        </div>
      ) : error ? (
        // A hard query failure (not a per-source error) — the whole query
        // failed. Per-source errors degrade gracefully below instead.
        <div
          className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-[13px] text-destructive"
          data-testid="proposals-error"
        >
          {t('proposals.error')}
        </div>
      ) : totalRows === 0 && (inbox?.sources ?? []).every((s) => !s.error) ? (
        <div
          className="rounded-md border border-dashed p-8 text-center text-[13px] text-muted-foreground"
          data-testid="proposals-empty"
        >
          {t('proposals.empty')}
        </div>
      ) : (
        <div className="space-y-5" data-testid="proposals-groups">
          {groups.map((g) => (
            <ProposalSourceGroup
              key={g.origin}
              origin={g.origin}
              rows={g.rows}
              error={g.source?.error ?? null}
              onOpenRow={onOpenRow}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ProposalSourceGroup({
  origin,
  rows,
  error,
  onOpenRow,
}: {
  origin: ProposalOrigin;
  rows: ProposalInboxRow[];
  error: Error | null;
  onOpenRow: (row: ProposalInboxRow) => void;
}) {
  const { t } = useTranslation('knowledge');
  const Icon = ORIGIN_ICON[origin];

  return (
    <section data-testid={`proposals-group-${origin}`}>
      <div className="mb-2 flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t(`proposals.originLabel.${origin}`)}
        </h3>
        <span
          className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground"
          data-testid={`proposals-count-${origin}`}
        >
          {error ? '!' : rows.length}
        </span>
      </div>

      {error ? (
        <div
          className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2.5 text-[12px] text-amber-700 dark:text-amber-400"
          data-testid={`proposals-source-error-${origin}`}
          role="status"
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {t('proposals.sourceError')}
        </div>
      ) : rows.length === 0 ? (
        <p
          className="rounded-md border border-dashed px-3 py-3 text-[12px] text-muted-foreground"
          data-testid={`proposals-group-empty-${origin}`}
        >
          {t('proposals.empty')}
        </p>
      ) : (
        <ul className="divide-y rounded-md border" data-testid={`proposals-list-${origin}`}>
          {rows.map((row) => (
            <li key={`${row.origin}:${row.id}`}>
              <button
                type="button"
                onClick={() => onOpenRow(row)}
                data-testid={`proposals-row-${row.origin}-${row.id}`}
                data-deeplink={row.deepLinkUrl}
                aria-label={t('proposals.openRow', { title: row.title })}
                className={cn(
                  'flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/50',
                )}
              >
                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {t(`proposals.origin.${row.origin}`)}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                  {row.title}
                </span>
                <span className="flex shrink-0 items-center gap-1 text-[12px] text-primary">
                  {t('proposals.review')}
                  <ChevronRight className="h-3.5 w-3.5" />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
