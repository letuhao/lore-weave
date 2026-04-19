import { useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Eye, History, RotateCcw, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { isVersionConflict } from '../api';
import { useGlobalSummaryVersions } from '../hooks/useSummaryVersions';
import type { Summary, SummaryVersion } from '../types';

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

      {/* Preview modal */}
      {previewVersion && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setPreviewVersion(null)}
          role="presentation"
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-lg border bg-background shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="preview-title"
          >
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <h3
                  id="preview-title"
                  className="font-serif text-sm font-semibold"
                >
                  {t('global.versions.previewTitle', {
                    version: previewVersion.version,
                  })}
                </h3>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {formatTimestamp(previewVersion.created_at)} ·{' '}
                  {t(`global.versions.source.${previewVersion.edit_source}`)}
                </p>
              </div>
              <button
                onClick={() => setPreviewVersion(null)}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                aria-label={t('global.versions.close')}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap px-4 py-3 font-mono text-xs leading-relaxed">
              {previewVersion.content || t('global.versions.emptyContent')}
            </pre>
            <div className="flex items-center justify-end gap-2 border-t bg-muted/20 px-4 py-3">
              <button
                onClick={() => setPreviewVersion(null)}
                className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {t('global.versions.close')}
              </button>
              <button
                onClick={() => {
                  setConfirmRollback(previewVersion);
                  setPreviewVersion(null);
                }}
                disabled={currentSummary == null || isRollingBack}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {t('global.versions.rollbackFromPreview')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rollback confirmation */}
      {confirmRollback && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmRollback(null)}
          role="presentation"
        >
          <div
            className="w-full max-w-sm rounded-lg border bg-background p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="alertdialog"
            aria-labelledby="rollback-title"
            aria-describedby="rollback-desc"
          >
            <h3
              id="rollback-title"
              className="mb-1 font-serif text-sm font-semibold"
            >
              {t('global.versions.confirmTitle')}
            </h3>
            <p
              id="rollback-desc"
              className="mb-4 text-[12px] text-muted-foreground"
            >
              {t('global.versions.confirmBody', {
                version: confirmRollback.version,
              })}
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmRollback(null)}
                className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {t('projects.form.cancel')}
              </button>
              <button
                onClick={() => void handleRollback(confirmRollback)}
                disabled={isRollingBack}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isRollingBack
                  ? t('global.versions.rollingBack')
                  : t('global.versions.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
