// EC-3 — the divergence (dị bản) MANAGE view. Canonical + named derivatives, each with
// Switch-to / Archive, the read-only spec of the selected one, and the create wizard.
// Logic lives in useDivergenceManager; this renders only.
import { useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { derivativeName, useDivergenceManager } from '../hooks/useDivergenceManager';
import type { Work } from '../types';
import { DivergenceWizard } from './DivergenceWizard';
import { BranchDiffView } from './BranchDiffView';

export function DivergenceManagerView({ bookId, token }: { bookId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const m = useDivergenceManager(bookId, token);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [detailTab, setDetailTab] = useState<'spec' | 'diff'>('spec');
  const canonical = m.canonical; // local so TS narrows it to Work past the guard below

  const status = m.resolution.data?.status;
  if (m.resolution.isLoading) {
    return <div data-testid="divergence-loading" className="p-4 text-sm text-muted-foreground">{t('divergence.loading', { defaultValue: 'Loading works…' })}</div>;
  }
  if (status === 'unavailable') {
    return <div data-testid="divergence-unavailable" className="p-4 text-sm text-amber-600">{t('divergence.unavailable', { defaultValue: 'Composition service is unavailable — try again shortly.' })}</div>;
  }
  if (!canonical) {
    // No composition Work at all — a dị bản branches from a canon that must exist first.
    return (
      <div data-testid="divergence-nowork" className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        {t('divergence.noWork', { defaultValue: 'This book has no plan yet — lay out its arcs and chapters first, then branch a what-if here.' })}
      </div>
    );
  }

  const isActive = (w: Work) => m.activeProjectId === w.project_id;

  const doSwitch = async (w: Work | null) => {
    const ok = await m.switchTo(w ? w.project_id : null);
    if (!ok) toast.error(t('divergence.switchFailed', { defaultValue: 'Could not switch — try again.' }));
  };
  const doArchive = (w: Work) => {
    m.archive.mutate(w, {
      onSuccess: () => toast.success(t('divergence.archived', { defaultValue: 'Archived — its chapters and knowledge are kept; it left this list.' })),
      onError: (e) => {
        const conflict = (e as { status?: number }).status === 412;
        toast[conflict ? 'warning' : 'error'](
          conflict
            ? t('divergence.archiveConflict', { defaultValue: 'Changed elsewhere — reloaded.' })
            : t('divergence.archiveFailed', { defaultValue: 'Could not archive — try again.' }),
        );
        if (m.selectedProjectId === w.project_id) m.setSelectedProjectId(null);
      },
    });
  };

  const Row = ({ w, canon }: { w: Work; canon: boolean }) => {
    const active = isActive(w);
    const name = derivativeName(w) ?? (canon ? t('divergence.canonical', { defaultValue: 'Canonical' }) : t('divergence.unnamed', { defaultValue: 'Untitled dị bản' }));
    const selectable = !canon; // only a derivative opens a spec
    const select = () => m.setSelectedProjectId(w.project_id === m.selectedProjectId ? null : w.project_id);
    // A plain div (NOT a <button>) so the Switch/Archive <button>s below are not nested
    // inside a button (invalid content model / a11y). Derivative rows are keyboard-
    // operable via role+tabIndex; the canon row is static.
    return (
      <div
        data-testid={canon ? 'divergence-canon-row' : `divergence-row-${w.project_id}`}
        {...(selectable ? { role: 'button', tabIndex: 0, onClick: select, onKeyDown: (e: ReactKeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); } } } : {})}
        className={`flex w-full flex-col gap-1 rounded border px-2.5 py-2 text-left ${selectable ? 'cursor-pointer' : ''} ${
          active ? 'border-emerald-400 bg-emerald-50/40 dark:border-emerald-600 dark:bg-emerald-950/20' : 'border-border hover:border-foreground/30'
        } ${m.selectedProjectId === w.project_id ? 'ring-1 ring-primary' : ''}`}
      >
        <div className="flex items-center gap-2">
          <span className="flex-1 truncate text-[13px] font-medium">{name}</span>
          {active && <span data-testid="divergence-active-badge" className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200">{t('divergence.active', { defaultValue: 'active' })}</span>}
          {canon && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900 dark:text-amber-200">{t('divergence.canonTag', { defaultValue: 'canon' })}</span>}
        </div>
        {!canon && (
          <div className="text-[11px] text-muted-foreground">
            {w.branch_point != null
              ? t('divergence.branchedAt', { defaultValue: 'branched at chapter {{n}}', n: w.branch_point + 1 })
              : t('divergence.branchedUnknown', { defaultValue: 'branch point unknown' })}
          </div>
        )}
        <div className="mt-0.5 flex items-center gap-1.5">
          {!active && (
            <button
              type="button"
              data-testid={`divergence-switch-${w.project_id}`}
              disabled={m.isSwitching}
              onClick={(e) => { e.stopPropagation(); void doSwitch(canon ? null : w); }}
              className="rounded border border-border px-2 py-0.5 text-[11px] hover:bg-muted disabled:opacity-50"
            >
              {t('divergence.switchTo', { defaultValue: 'Switch to' })}
            </button>
          )}
          {!canon && (
            <button
              type="button"
              data-testid={`divergence-archive-${w.project_id}`}
              onClick={(e) => { e.stopPropagation(); doArchive(w); }}
              className="rounded px-2 py-0.5 text-[11px] text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
            >
              {t('divergence.archive', { defaultValue: 'Archive' })}
            </button>
          )}
        </div>
      </div>
    );
  };

  const s = m.spec.data;

  return (
    <div data-testid="divergence-panel" className="flex h-full flex-col overflow-y-auto p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('divergence.title', { defaultValue: 'Divergence (dị bản)' })}</span>
        <button
          type="button"
          data-testid="divergence-new"
          onClick={() => setWizardOpen(true)}
          className="rounded bg-primary px-2 py-1 text-[12px] font-medium text-primary-foreground"
        >
          + {t('divergence.new', { defaultValue: 'New divergence' })}
        </button>
      </div>

      {/* Canonical */}
      <div className="mb-3 flex flex-col gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('divergence.canonicalSection', { defaultValue: 'Canonical' })}</span>
        <Row w={canonical} canon />
      </div>

      {/* Derivatives */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('divergence.derivativesSection', { defaultValue: 'Derivatives ({{n}})', n: m.derivatives.length })}
        </span>
        {m.derivatives.length === 0 ? (
          <div data-testid="divergence-empty" className="rounded border border-dashed border-border p-3 text-center text-[12px] text-muted-foreground">
            {t('divergence.emptyDerivatives', { defaultValue: 'No what-if branches yet. A dị bản branches your book at a chapter and diverges — the source stays read-only canon.' })}
          </div>
        ) : (
          m.derivatives.map((w) => <Row key={w.project_id} w={w} canon={false} />)
        )}
      </div>

      {/* Detail of the selected derivative — Spec (how it was declared) / Diff (what changed) */}
      {m.selected && (
        <div data-testid="divergence-detail" className="mt-3 rounded border border-border">
          <div className="flex items-center gap-1 border-b border-border px-2.5 py-1.5">
            <span className="mr-1 flex-1 truncate text-[12px] font-medium">{derivativeName(m.selected) ?? t('divergence.unnamed', { defaultValue: 'Untitled dị bản' })}</span>
            <button type="button" data-testid="divergence-tab-spec" onClick={() => setDetailTab('spec')} className={`rounded px-2 py-0.5 text-[11px] ${detailTab === 'spec' ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{t('divergence.tabSpec', { defaultValue: 'Spec' })}</button>
            <button type="button" data-testid="divergence-tab-diff" onClick={() => setDetailTab('diff')} className={`rounded px-2 py-0.5 text-[11px] ${detailTab === 'diff' ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{t('divergence.tabDiff', { defaultValue: 'Diff' })}</button>
          </div>

          {detailTab === 'spec' ? (
            <div className="p-2.5">
              {m.spec.isLoading ? (
                <div className="text-[11px] text-muted-foreground">{t('divergence.specLoading', { defaultValue: 'Loading spec…' })}</div>
              ) : m.spec.isError ? (
                <div data-testid="divergence-spec-error" className="text-[11px] text-red-600">{t('divergence.specError', { defaultValue: 'Could not load the branch spec — try reselecting it.' })}</div>
              ) : s ? (
                <dl className="grid grid-cols-[80px_1fr] gap-x-2 gap-y-1 text-[11px]">
                  <dt className="text-muted-foreground">{t('divergence.taxonomy', { defaultValue: 'Taxonomy' })}</dt>
                  <dd data-testid="divergence-spec-taxonomy">{s.taxonomy ?? '—'}</dd>
                  <dt className="text-muted-foreground">{t('divergence.branchPoint', { defaultValue: 'Branch point' })}</dt>
                  <dd>{s.branch_point != null ? t('divergence.chapterN', { defaultValue: 'chapter {{n}}', n: s.branch_point + 1 }) : '—'}</dd>
                  <dt className="text-muted-foreground">{t('divergence.canonRules', { defaultValue: 'Canon rules' })}</dt>
                  <dd>{s.canon_rules.length ? <ul className="list-disc pl-4">{s.canon_rules.map((r, i) => <li key={i}>{r}</li>)}</ul> : '—'}</dd>
                  <dt className="text-muted-foreground">{t('divergence.overrides', { defaultValue: 'Overrides' })}</dt>
                  <dd>{s.overrides.length ? t('divergence.nOverrides', { defaultValue: '{{n}} entity override(s)', n: s.overrides.length }) : '—'}</dd>
                </dl>
              ) : null}
              <p className="mt-2 text-[10px] leading-snug text-muted-foreground">
                {t('divergence.specImmutable', { defaultValue: 'The spec is written once, at derive. Editing it is not available yet — archive and re-derive to change it.' })}
              </p>
            </div>
          ) : (
            <div className="h-72">
              <BranchDiffView derivativeProjectId={m.selected.project_id} sourceProjectId={s?.source_project_id ?? null} token={token} />
            </div>
          )}
        </div>
      )}

      {wizardOpen && (
        <DivergenceWizard
          open={wizardOpen}
          onOpenChange={setWizardOpen}
          sourceWork={canonical}
          token={token}
          onDerived={(d) => {
            m.invalidate();
            // Auto-switch the studio to the freshly-spawned dị bản (the user just made it).
            void m.switchTo(d.project_id);
            setWizardOpen(false);
          }}
        />
      )}
    </div>
  );
}
