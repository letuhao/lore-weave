import { useEffect, useMemo, useRef, useState } from 'react';
import { diffLines, type Change } from 'diff';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Eye, History, RotateCcw, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ConfirmDialog, FormDialog } from '@/components/shared';
import { isVersionConflict } from '../api';
import { useGlobalSummaryVersions } from '../hooks/useSummaryVersions';
import type { Summary, SummaryVersion } from '../types';

// 14_kg_panels.md A3/K8 — DOCK-9 adoption precedent for this cycle: the preview + rollback-
// confirm modals were hand-rolled `fixed inset-0` overlays (docs/standards/dockable-gui.md
// DOCK-9); migrated onto the shared FormDialog/ConfirmDialog (Radix-portal-based), mirroring
// Glossary's ResolveKindModal precedent (13_glossary_panels.md A4).

// D-K8-01: inline history panel for the global summary bio.
// Lives below the editor textarea in GlobalBioTab. Shows archived
// versions newest-first with timestamp + truncated preview +
// View/Rollback actions. Clicking View opens a preview modal.
// Rollback creates a new live version (never rewinds) and
// invalidates the bio query so the editor re-syncs automatically.
//
// Takes the current Summary as a prop so it can pass the expected
// version through to the rollback mutation (If-Match discipline).

interface Props {
  currentSummary: Summary | null;
  onClose: () => void;
}

export function VersionsPanel({ currentSummary, onClose }: Props) {
  const { t, i18n } = useTranslation('knowledge');
  const { items, isLoading, isError, error, rollback, isRollingBack } =
    useGlobalSummaryVersions();
  const [previewVersion, setPreviewVersion] = useState<SummaryVersion | null>(
    null,
  );
  const [confirmRollback, setConfirmRollback] =
    useState<SummaryVersion | null>(null);
  // K19c.3-delta: toggle between full-text preview and a line-level
  // diff against the current live bio. Starts off (plain preview)
  // because users usually want to see the old version verbatim first
  // and toggle diff only when curious about "what changed".
  const [showDiff, setShowDiff] = useState(false);

  // 14_kg_panels.md A3 /review-impl MED — Radix keeps FormDialog/ConfirmDialog mounted during
  // their ~150ms exit animation (K8.2-R6, the same fix ProjectsBrowser's archive/delete
  // ConfirmDialogs already needed). Clearing `previewVersion`/`confirmRollback` to null to CLOSE
  // the dialog would otherwise blank the title/description/body mid-fade — a flash that never
  // existed before this DOCK-9 migration (the hand-rolled overlay unmounted instantly, no
  // animation). Keep the last-shown version so the closing dialog still renders real content.
  const lastPreview = useRef<SummaryVersion | null>(null);
  if (previewVersion) lastPreview.current = previewVersion;
  const displayedPreview = previewVersion ?? lastPreview.current;

  const lastConfirmRollback = useRef<SummaryVersion | null>(null);
  if (confirmRollback) lastConfirmRollback.current = confirmRollback;
  const displayedConfirmRollback = confirmRollback ?? lastConfirmRollback.current;

  // Memoise so the diff only re-runs when the preview target changes. Reads `displayedPreview`
  // (not `previewVersion`) so the diff stays intact during the FormDialog close animation too.
  const diffChanges = useMemo<Change[]>(() => {
    if (!displayedPreview) return [];
    const base = currentSummary?.content ?? '';
    return diffLines(base, displayedPreview.content);
  }, [displayedPreview, currentSummary?.content]);

  // Reset the diff toggle whenever the preview target changes so
  // opening a new preview always starts in plain-text mode.
  useEffect(() => {
    setShowDiff(false);
  }, [previewVersion?.version]);

  const formatTimestamp = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language);

  const handleRollback = async (v: SummaryVersion) => {
    if (currentSummary == null) return;
    try {
      await rollback({
        version: v.version,
        expectedVersion: currentSummary.version,
      });
      toast.success(t('global.versions.rollbackSuccess'));
      setConfirmRollback(null);
      setPreviewVersion(null);
    } catch (err) {
      // D-K8-03: rollback honours If-Match too — a concurrent edit
      // to the live bio gives the user a stale expectedVersion.
      // The parent GlobalBioTab will pick up the fresh version on
      // the next refetch; here we just show a toast telling them
      // to refresh.
      if (isVersionConflict<Summary>(err)) {
        toast.error(t('global.conflict'));
      } else {
        toast.error(
          err instanceof Error ? err.message : t('global.versions.rollbackFailed'),
        );
      }
    }
  };

  return (
    <>
      <div className="mt-4 rounded-lg border bg-card/40">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <div className="flex items-center gap-2">
            <History className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-serif text-xs font-semibold">
              {t('global.versions.title')}
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label={t('global.versions.close')}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {isLoading && (
          <p className="px-3 py-4 text-[11px] text-muted-foreground">
            {t('global.versions.loading')}
          </p>
        )}

        {isError && (
          <p className="px-3 py-4 text-[11px] text-destructive">
            {t('global.versions.loadFailed', {
              error: error instanceof Error ? error.message : 'unknown error',
            })}
          </p>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <p className="px-3 py-4 text-[11px] text-muted-foreground">
            {t('global.versions.empty')}
          </p>
        )}

        {!isLoading && !isError && items.length > 0 && (
          <ul className="divide-y">
            {items.map((v) => (
              <li
                key={v.version_id}
                className="flex items-center gap-3 px-3 py-2 text-[11px]"
              >
                <div className="min-w-0 flex-1">
                  <div className="mb-0.5 flex items-center gap-2">
                    <span className="font-mono font-semibold">
                      {t('global.versions.versionLabel', { version: v.version })}
                    </span>
                    <span
                      className={cn(
                        'rounded-sm px-1 py-0.5 text-[9px] font-medium uppercase',
                        v.edit_source === 'rollback'
                          ? 'bg-warning/20 text-warning'
                          : 'bg-muted text-muted-foreground',
                      )}
                    >
                      {t(`global.versions.source.${v.edit_source}`)}
                    </span>
                    <span className="text-muted-foreground">
                      {formatTimestamp(v.created_at)}
                    </span>
                  </div>
                  <p className="truncate text-muted-foreground">
                    {v.content.slice(0, 120) || t('global.versions.emptyContent')}
                  </p>
                </div>
                <div className="flex flex-shrink-0 gap-1">
                  <button
                    onClick={() => setPreviewVersion(v)}
                    title={t('global.versions.view')}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => setConfirmRollback(v)}
                    disabled={currentSummary == null || isRollingBack}
                    title={t('global.versions.rollback')}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Preview modal — FormDialog (DOCK-9 adoption, 14_kg_panels.md A3) */}
      <FormDialog
        open={previewVersion !== null}
        onOpenChange={(o) => !o && setPreviewVersion(null)}
        size="2xl"
        title={
          displayedPreview
            ? t('global.versions.previewTitle', { version: displayedPreview.version })
            : ''
        }
        description={
          displayedPreview
            ? `${formatTimestamp(displayedPreview.created_at)} · ${t(`global.versions.source.${displayedPreview.edit_source}`)}`
            : undefined
        }
        footer={
          <>
            <button
              onClick={() => setPreviewVersion(null)}
              className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              {t('global.versions.close')}
            </button>
            <button
              onClick={() => {
                if (previewVersion) setConfirmRollback(previewVersion);
                setPreviewVersion(null);
              }}
              disabled={currentSummary == null || isRollingBack}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {t('global.versions.rollbackFromPreview')}
            </button>
          </>
        }
      >
        {displayedPreview && (
          <>
            {/* K19c.3-delta: Show-diff toggle. When off, render the
                version's full text as before. When on, render a
                line-level diff against the current live bio. */}
            <div className="mb-2 flex items-center justify-end gap-2">
              <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <input
                  type="checkbox"
                  checked={showDiff}
                  onChange={(e) => setShowDiff(e.target.checked)}
                  data-testid="versions-diff-toggle"
                />
                {t('global.versions.diffToggle')}
              </label>
            </div>
            {showDiff ? (
              <div
                className="font-mono text-xs leading-relaxed"
                data-testid="versions-diff-view"
              >
                {diffChanges.length === 0 ||
                (diffChanges.length === 1 && !diffChanges[0].added && !diffChanges[0].removed) ? (
                  <p className="text-[11px] text-muted-foreground">
                    {t('global.versions.diffEmpty')}
                  </p>
                ) : (
                  diffChanges.map((change, idx) => (
                    <pre
                      key={idx}
                      className={cn(
                        'whitespace-pre-wrap',
                        change.added &&
                          'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
                        change.removed &&
                          'bg-destructive/10 text-destructive line-through',
                        !change.added && !change.removed && 'text-muted-foreground',
                      )}
                      data-diff-kind={
                        change.added ? 'added' : change.removed ? 'removed' : 'context'
                      }
                    >
                      {change.value}
                    </pre>
                  ))
                )}
              </div>
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">
                {displayedPreview.content || t('global.versions.emptyContent')}
              </pre>
            )}
          </>
        )}
      </FormDialog>

      {/* Rollback confirmation — ConfirmDialog (DOCK-9 adoption, 14_kg_panels.md A3) */}
      <ConfirmDialog
        open={confirmRollback !== null}
        onOpenChange={(o) => !o && setConfirmRollback(null)}
        title={t('global.versions.confirmTitle')}
        description={
          displayedConfirmRollback
            ? t('global.versions.confirmBody', { version: displayedConfirmRollback.version })
            : ''
        }
        confirmLabel={isRollingBack ? t('global.versions.rollingBack') : t('global.versions.confirm')}
        cancelLabel={t('projects.form.cancel')}
        onConfirm={() => confirmRollback && void handleRollback(confirmRollback)}
        loading={isRollingBack}
      />
    </>
  );
}
