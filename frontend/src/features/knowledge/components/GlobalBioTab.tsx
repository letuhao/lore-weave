import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/shared';
import { useSummaries } from '../hooks/useSummaries';

// Mirrors SummaryContent = Annotated[str, StringConstraints(max_length=50000)]
// in services/knowledge-service/app/db/models.py. Same pattern as
// ProjectFormModal's caps — immediate feedback instead of a 422.
const CONTENT_MAX = 50000;

export function GlobalBioTab() {
  const { t } = useTranslation('memory');
  const { global, isLoading, isError, error, updateGlobal, isUpdatingGlobal } =
    useSummaries();

  const [content, setContent] = useState('');
  // Track the server-side content we last synced against so we can
  // detect unsaved edits without making setState in the render path.
  const [baseline, setBaseline] = useState('');
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
    if (contentRef.current === baselineRef.current) {
      // No unsaved edits — sync both from the server.
      setContent(next);
      setBaseline(next);
      return;
    }
    // Gate-5-I3: when the server has caught up to our local
    // content, our save just landed. Advance the baseline so the
    // dirty flag clears and the "Unsaved changes" badge goes
    // away. Don't touch `content` (already equals next).
    if (contentRef.current === next) {
      setBaseline(next);
      return;
    }
    // Otherwise the user has unsaved edits AND the server differs
    // — keep local edits, same lost-update surface tracked as
    // D-K8-03. K8.3-R4 protects in-flight typing.
  }, [global?.content, global?.version]);

  const trimmed = content.trim();
  const contentValid = content.length <= CONTENT_MAX;
  // K8.3-R2: compare trimmed so whitespace-only edits against an
  // empty baseline don't enable a no-op Save request.
  const dirty = trimmed !== baseline.trim();
  const canSave = dirty && contentValid && !isUpdatingGlobal;

  const handleSave = async () => {
    if (!canSave) return;
    try {
      // K8.3-R5: preserve the user's internal formatting (e.g.
      // trailing newlines for markdown paragraphs). Only collapse
      // the whitespace-only case to "" so it acts as a clear, since
      // the backend treats "" as "no global bio set".
      const payload = trimmed === '' ? '' : content;
      await updateGlobal({ content: payload });
      toast.success(t('global.saved'));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('global.saveFailed'));
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
              {global?.version != null && (
                <span className="ml-3">{t('global.version', { version: global.version })}</span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {dirty && (
                <span className="text-[11px] text-warning">{t('global.unsavedChanges')}</span>
              )}
              <button
                onClick={() => void handleSave()}
                disabled={!canSave}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isUpdatingGlobal ? t('global.saving') : t('global.save')}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
