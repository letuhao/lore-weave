import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/shared';
import { cn } from '@/lib/utils';
import { isVersionConflict } from '../../api';
import { useSummaries } from '../../hooks/useSummaries';
import { TOUCH_TARGET_CLASS } from '../../lib/touchTarget';
import type { Summary } from '../../types';

// K19f.4 — mobile Global bio editor. Stripped down from GlobalBioTab:
//   DROPPED: Reset button, Regenerate dialog, Versions panel,
//   PreferencesSection, token estimate, version counter
//   KEPT:    textarea + save + char count + dirty indicator + the
//            full If-Match conflict handling from desktop
//
// If-Match is NOT dropped — correctness > simplicity. A mobile user
// saving on top of a stale baseline while desktop has newer content
// must not silently stomp the desktop edit. Same 412-absorb pattern
// as the desktop tab so cross-device races surface as a toast + reset
// baseline instead of data loss.

// Mirrors SummaryContent = Annotated[str, StringConstraints(max_length=50000)]
// in services/knowledge-service/app/db/models.py.
const CONTENT_MAX = 50000;

export function GlobalMobile() {
  const { t } = useTranslation('knowledge');
  const { global, isLoading, isError, error, updateGlobal, isUpdatingGlobal } =
    useSummaries();

  const [content, setContent] = useState('');
  const [baseline, setBaseline] = useState('');
  const [baselineVersion, setBaselineVersion] = useState<number | null>(null);

  // Same ref pattern as GlobalBioTab — read latest values inside the
  // sync effect without re-subscribing. See GlobalBioTab's K8.3-R4
  // comment for the race this prevents.
  const contentRef = useRef(content);
  const baselineRef = useRef(baseline);
  contentRef.current = content;
  baselineRef.current = baseline;

  useEffect(() => {
    const next = global?.content ?? '';
    const nextVersion = global?.version ?? null;
    if (contentRef.current === baselineRef.current) {
      setContent(next);
      setBaseline(next);
      setBaselineVersion(nextVersion);
      return;
    }
    if (contentRef.current === next) {
      setBaseline(next);
      setBaselineVersion(nextVersion);
      return;
    }
    // Unsaved local edits win — save will 412-handle if the server
    // differs, same as desktop.
  }, [global?.content, global?.version]);

  const trimmed = content.trim();
  const contentValid = content.length <= CONTENT_MAX;
  const dirty = trimmed !== baseline.trim();
  const canSave = dirty && contentValid && !isUpdatingGlobal;

  const handleSave = async () => {
    if (!canSave) return;
    try {
      const payload = trimmed === '' ? '' : content;
      await updateGlobal({
        payload: { content: payload },
        expectedVersion: baselineVersion,
      });
      toast.success(t('mobile.global.saved'));
    } catch (err) {
      if (isVersionConflict<Summary>(err)) {
        setBaseline(err.current.content);
        setBaselineVersion(err.current.version);
        toast.error(t('mobile.global.conflict'));
      } else {
        toast.error(
          err instanceof Error ? err.message : t('mobile.global.saveFailed'),
        );
      }
    }
  };

  return (
    <div data-testid="mobile-global">
      {isLoading && <Skeleton className="h-40 w-full" />}

      {isError && !isLoading && (
        <div
          className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive"
          data-testid="mobile-global-error"
        >
          {t('mobile.global.loadFailed', {
            error: error instanceof Error ? error.message : 'unknown error',
          })}
        </div>
      )}

      {!isLoading && !isError && (
        <>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={CONTENT_MAX}
            rows={12}
            className="w-full resize-y rounded-md border bg-input px-3 py-2 font-mono text-[13px] leading-relaxed outline-none focus:border-ring"
            placeholder={t('mobile.global.placeholder')}
            data-testid="mobile-global-textarea"
          />

          <div className="mt-2 flex items-center justify-between gap-2 text-[11px]">
            <span className="text-muted-foreground tabular-nums">
              {content.length.toLocaleString()} / {CONTENT_MAX.toLocaleString()}
            </span>
            <div className="flex items-center gap-2">
              {dirty && (
                <span
                  className="text-warning"
                  data-testid="mobile-global-unsaved"
                >
                  {t('mobile.global.unsaved')}
                </span>
              )}
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={!canSave}
                className={cn(
                  TOUCH_TARGET_CLASS,
                  'rounded-md bg-primary px-4 text-[13px] font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50',
                )}
                data-testid="mobile-global-save"
              >
                {isUpdatingGlobal
                  ? t('mobile.global.saving')
                  : t('mobile.global.save')}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
