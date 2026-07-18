// S-10 O3 — the Issues tab feed. Renders the book's ranked problems (error → warn → info) from the
// diagnostics REST twin; each row DEEP-LINKS to the panel that owns the fix (the spec's core: an
// issue you can't act on is a dead end). Self-contained (host + auth + query) so the bottom panel
// stays thin and provider-free in its own test.
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';
import { useBookDiagnostics } from '../hooks/useBookDiagnostics';

// Which panel owns the fix for each diagnostic kind (the deep-link target). A kind with no mapping
// still renders — it just isn't clickable (no owning panel to send the user to).
const KIND_PANEL: Record<string, string> = {
  conformance_never_run: 'quality-conformance',
  conformance_dirty: 'quality-conformance',
  index_stale: 'quality-conformance',
  canon_contradiction: 'quality-canon',
  broken_canon_rule: 'quality-canon-rules',
  open_thread_debt: 'quality-promises',
  unplanned_chapter: 'plan-hub',
  prose_deleted_spec_node: 'plan-hub',
};

const SEV_STYLE: Record<string, string> = {
  error: 'bg-destructive/15 text-destructive',
  warn: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  info: 'bg-muted text-muted-foreground',
};

export function StudioIssuesFeed() {
  const { t } = useTranslation('studio');
  const { bookId, openPanel } = useStudioHost();
  const diag = useBookDiagnostics(bookId, true);

  if (diag.isLoading) {
    return <Centered>{t('bottom.issuesLoading', { defaultValue: 'Checking for problems…' })}</Centered>;
  }
  if (diag.isError) {
    return (
      <Centered tone="error" testid="studio-issues-error">
        {t('bottom.issuesError', { defaultValue: 'Could not load the problems panel.' })}
      </Centered>
    );
  }
  if (diag.items.length === 0 && diag.warnings.length === 0) {
    return (
      <Centered testid="studio-issues-empty">
        {t('bottom.issuesEmpty', { defaultValue: 'No problems found in this book.' })}
      </Centered>
    );
  }

  return (
    <div data-testid="studio-issues-feed" className="flex h-full min-h-0 flex-col overflow-y-auto p-1 text-left">
      {diag.warnings.map((w, i) => (
        <div key={`w${i}`} data-testid="studio-issues-warning" className="px-2 py-1 text-[10px] text-amber-600 dark:text-amber-400">
          ⚠ {w}
        </div>
      ))}
      <ul className="flex flex-col">
        {diag.items.map((it, i) => {
          const panel = KIND_PANEL[it.kind];
          const clickable = !!panel;
          return (
            <li
              key={`${it.kind}-${i}`}
              data-testid={`studio-issue-${it.kind}`}
              className={cn(
                'flex items-start gap-2 border-b px-2 py-1.5',
                clickable && 'cursor-pointer hover:bg-secondary',
              )}
              // Deep-link to the OWNING panel, and — when the diagnostic carries them — the
              // panel-appropriate focus params (e.g. focusRuleId / focusChapterId) so the row jumps to
              // the exact offending item, not just the panel.
              onClick={clickable ? () => openPanel(panel, { focus: true, params: { bookId, ...(it.focus ?? {}) } }) : undefined}
            >
              <span className={cn('mt-0.5 rounded px-1 py-0.5 text-[9px] font-semibold uppercase', SEV_STYLE[it.severity] ?? SEV_STYLE.info)}>
                {t(`bottom.sev.${it.severity}`, { defaultValue: it.severity })}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] text-foreground/90">{it.title}</span>
                {it.detail && <span className="block truncate text-[10px] text-muted-foreground">{it.detail}</span>}
              </span>
              {clickable && <span className="mt-0.5 text-[10px] text-muted-foreground">→</span>}
            </li>
          );
        })}
      </ul>
      {diag.refsCapped && (
        <div data-testid="studio-issues-capped" className="px-2 py-1 text-center text-[10px] text-muted-foreground">
          {t('bottom.issuesCapped', { total: diag.total, defaultValue: 'showing the top rows of {{total}}' })}
        </div>
      )}
    </div>
  );
}

function Centered({ children, tone, testid }: { children: React.ReactNode; tone?: 'error'; testid?: string }) {
  return (
    <div
      data-testid={testid}
      className={cn('flex h-full items-center justify-center p-4 text-center text-[11px]', tone === 'error' ? 'text-destructive' : 'text-muted-foreground')}
    >
      {children}
    </div>
  );
}
