import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { History, RotateCcw } from 'lucide-react';
import { FormDialog, Skeleton } from '@/components/shared';
import { isVersionConflict } from '../api';
import { useSummaries } from '../hooks/useSummaries';
import type { Summary } from '../types';
import { VersionsPanel } from './VersionsPanel';
import { PreferencesSection } from './PreferencesSection';

// Mirrors SummaryContent = Annotated[str, StringConstraints(max_length=50000)]
// in services/knowledge-service/app/db/models.py. Same pattern as
// ProjectFormModal's caps — immediate feedback instead of a 422.
const CONTENT_MAX = 50000;

// K19c.1-delta: rough GPT token count. chars/4 is the documented
// heuristic for English prose (OpenAI cookbook); close enough for
// a live counter. A real tiktoken-port would be more accurate for
// CJK-heavy content but adds ~200KB to the bundle.
function estimateTokens(content: string): number {
  return Math.ceil(content.length / 4);
}

export function GlobalBioTab() {
  const { t } = useTranslation('knowledge');
  const { global, isLoading, isError, error, updateGlobal, isUpdatingGlobal } =
    useSummaries();
  // D-K8-01: history panel toggle. Starts collapsed so the initial
  // Knowledge page load stays cheap — the versions query only fires
  // when `showVersions` flips to true.
  const [showVersions, setShowVersions] = useState(false);
  // K19c.1-delta: Reset clears the bio to empty. Destructive enough
  // to warrant a confirm before firing the save.
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);

  const [content, setContent] = useState('');
  // Track the server-side content we last synced against so we can
  // detect unsaved edits without making setState in the render path.
  const [baseline, setBaseline] = useState('');
  // D-K8-03: track the version the `baseline` was captured at. null
  // means we've never seen a prior row (fresh user, no global bio),
  // which is the one case where PATCH without If-Match is legal.
  // Bumped on every successful save OR on a 412 (refreshed from the
  // server's current row).
  const [baselineVersion, setBaselineVersion] = useState<number | null>(null);
  // K8.3-R4: contentRef + baselineRef let the effect below read the
  // latest values without re-subscribing (would cause an infinite
  // loop). We need them to skip server-sync when the local buffer
  // has unsaved edits — otherwise the post-save react-query refetch
  // races ahead of the user's next keystrokes and wipes them.
  const contentRef = useRef(content);
  const baselineRef = useRef(baseline);
  contentRef.current = content;
  baselineRef.current = baseline;

  useEffect(() => {
    const next = global?.content ?? '';
    const nextVersion = global?.version ?? null;
    if (contentRef.current === baselineRef.current) {
      // No unsaved edits — sync both from the server.
      setContent(next);
      setBaseline(next);
      setBaselineVersion(nextVersion);
      return;
    }
    // Gate-5-I3: when the server has caught up to our local
    // content, our save just landed. Advance the baseline so the
    // dirty flag clears and the "Unsaved changes" badge goes
    // away. Don't touch `content` (already equals next).
    if (contentRef.current === next) {
      setBaseline(next);
      setBaselineVersion(nextVersion);
      return;
    }
    // Otherwise the user has unsaved edits AND the server differs
    // — keep local edits. handleSave will still send the stale
    // baselineVersion in If-Match; the backend will reject with
    // 412 and the handler refreshes from the response body.
  }, [global?.content, global?.version]);

  const trimmed = content.trim();
  const contentValid = content.length <= CONTENT_MAX;
  // K8.3-R2: compare trimmed so whitespace-only edits against an
  // empty baseline don't enable a no-op Save request.
  const dirty = trimmed !== baseline.trim();
  const canSave = dirty && contentValid && !isUpdatingGlobal;
  // K19c.1-delta: Reset is only useful when the SAVED bio has content.
  // If the baseline is already empty there's nothing to clear.
  const canReset =
    baseline.trim() !== '' && !isUpdatingGlobal && !resetting;
  const tokenEstimate = estimateTokens(content);

  const handleReset = async () => {
    // Server-side clear: PATCH /summaries/global with content="". Uses
    // the same If-Match discipline + 412 handler as handleSave. After
    // success, useEffect picks up the new baseline from the refetch.
    if (!canReset) return;
    setResetting(true);
    try {
      await updateGlobal({
        payload: { content: '' },
        expectedVersion: baselineVersion,
      });
      setContent('');
      toast.success(t('global.resetSuccess'));
      setConfirmReset(false);
    } catch (err) {
      if (isVersionConflict<Summary>(err)) {
        setBaseline(err.current.content);
        setBaselineVersion(err.current.version);
        toast.error(t('global.conflict'));
      } else {
        toast.error(err instanceof Error ? err.message : t('global.resetFailed'));
      }
    } finally {
      setResetting(false);
    }
  };

  const handleSave = async () => {
    if (!canSave) return;
    try {
      // K8.3-R5: preserve the user's internal formatting (e.g.
      // trailing newlines for markdown paragraphs). Only collapse
      // the whitespace-only case to "" so it acts as a clear, since
      // the backend treats "" as "no global bio set".
      const payload = trimmed === '' ? '' : content;
      await updateGlobal({
        payload: { content: payload },
        // D-K8-03: first save (no prior row) sends null; subsequent
        // saves send the version captured at the last sync.
        expectedVersion: baselineVersion,
      });
      toast.success(t('global.saved'));
    } catch (err) {
      // D-K8-03: 412 — another device beat us to it. Refresh the
      // baseline to the server's current row AND keep the user's
      // unsaved text so they can re-apply on top. The response body
      // is the fresh Summary.
      if (isVersionConflict<Summary>(err)) {
        setBaseline(err.current.content);
        setBaselineVersion(err.current.version);
        toast.error(
          t('global.conflict', {
            defaultValue:
              'Another device updated this bio. Review the latest and save again.',
          }),
        );
      } else {
        toast.error(err instanceof Error ? err.message : t('global.saveFailed'));
      }
    }
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="mb-1 font-serif text-sm font-semibold">{t('global.title')}</h2>
        <p className="text-[12px] text-muted-foreground">
          {t('global.description', { max: CONTENT_MAX.toLocaleString() })}
        </p>
      </div>

      {isLoading && <Skeleton className="h-40 w-full" />}

      {isError && !isLoading && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-xs text-destructive">
          {t('global.loadFailed', { error: error instanceof Error ? error.message : 'unknown error' })}
        </div>
      )}

      {!isLoading && !isError && (
        <>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={CONTENT_MAX}
            rows={14}
            className="w-full resize-y rounded-md border bg-input px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:border-ring"
            placeholder={t('global.placeholder')}
          />

          <div className="mt-2 flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">
              {content.length.toLocaleString()} / {CONTENT_MAX.toLocaleString()}
              <span
                className="ml-3"
                data-testid="global-token-estimate"
              >
                {t('global.tokenEstimate', {
                  tokens: tokenEstimate.toLocaleString(),
                })}
              </span>
              {global?.version != null && (
                <span className="ml-3">{t('global.version', { version: global.version })}</span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {dirty && (
                <span className="text-[11px] text-warning">{t('global.unsavedChanges')}</span>
              )}
              {/* D-K8-01: history toggle. Hidden until the summary
                  row actually exists — before first save there's
                  nothing to look at. */}
              {global != null && (
                <button
                  onClick={() => setShowVersions((v) => !v)}
                  className="flex items-center gap-1 rounded-md border px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                >
                  <History className="h-3 w-3" />
                  {t('global.versions.toggle')}
                </button>
              )}
              {/* K19c.1-delta: Reset button. Only meaningful when the
                  SAVED bio has content — disabled state hides it for
                  fresh users who haven't saved anything yet. */}
              <button
                onClick={() => setConfirmReset(true)}
                disabled={!canReset}
                className="flex items-center gap-1 rounded-md border border-destructive/30 px-2 py-1.5 text-[11px] text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="global-reset"
              >
                <RotateCcw className="h-3 w-3" />
                {t('global.reset')}
              </button>
              <button
                onClick={() => void handleSave()}
                disabled={!canSave}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isUpdatingGlobal ? t('global.saving') : t('global.save')}
              </button>
            </div>
          </div>

          {showVersions && (
            <VersionsPanel
              currentSummary={global}
              onClose={() => setShowVersions(false)}
            />
          )}

          {/* K19c.4: cross-project preferences extracted by Track 2. */}
          <PreferencesSection />

          {/* K19c.1-delta: Reset confirm dialog. */}
          {confirmReset && (
            <FormDialog
              open={true}
              onOpenChange={(o) => {
                if (!o && !resetting) setConfirmReset(false);
              }}
              title={t('global.resetConfirmTitle')}
              description={t('global.resetConfirmBody')}
              footer={
                <>
                  <button
                    onClick={() => setConfirmReset(false)}
                    disabled={resetting}
                    className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {t('global.resetCancel')}
                  </button>
                  <button
                    onClick={() => void handleReset()}
                    disabled={resetting}
                    className="rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="global-reset-confirm"
                  >
                    {resetting ? t('global.resetting') : t('global.resetConfirm')}
                  </button>
                </>
              }
            >
              <p className="text-[12px] text-muted-foreground">
                {t('global.resetConfirmNote')}
              </p>
            </FormDialog>
          )}
        </>
      )}
    </div>
  );
}
