import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Skeleton } from '@/components/shared';
import { useSummaries } from '../hooks/useSummaries';

// Mirrors SummaryContent = Annotated[str, StringConstraints(max_length=50000)]
// in services/knowledge-service/app/db/models.py. Same pattern as
// ProjectFormModal's caps — immediate feedback instead of a 422.
const CONTENT_MAX = 50000;

export function GlobalBioTab() {
  const { global, isLoading, isError, error, updateGlobal, isUpdatingGlobal } =
    useSummaries();

  const [content, setContent] = useState('');
  // Track the server-side content we last synced against so we can
  // detect unsaved edits without making setState in the render path.
  const [baseline, setBaseline] = useState('');

  // Pull server state into the textarea on first load and after a
  // successful save (react-query invalidation refreshes `global`).
  // Skipping the effect while editing would be nicer but needs a
  // dirty-flag heuristic — for Track 1, if the server version changes
  // while the user is editing we just prefer the server (D-K8-03 is
  // about the same lost-update class of bug).
  useEffect(() => {
    const next = global?.content ?? '';
    setContent(next);
    setBaseline(next);
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
      // Empty string clears the bio — backend accepts it as a delete
      // sentinel. Trim on send so whitespace-only is also a clear.
      await updateGlobal({ content: trimmed });
      toast.success('Global bio saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    }
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="mb-1 font-serif text-sm font-semibold">Global bio</h2>
        <p className="text-[12px] text-muted-foreground">
          A short description of you the AI can see in every project. Style
          preferences, context about your work, anything you want to carry
          across sessions. Max {CONTENT_MAX.toLocaleString()} characters.
        </p>
      </div>

      {isLoading && <Skeleton className="h-40 w-full" />}

      {isError && !isLoading && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-xs text-destructive">
          Failed to load summary: {error instanceof Error ? error.message : 'unknown error'}
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
            placeholder="e.g. I write urban fantasy. Keep names in Japanese order. Use sparing prose, no purple adjectives."
          />

          <div className="mt-2 flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">
              {content.length.toLocaleString()} / {CONTENT_MAX.toLocaleString()}
              {global?.version != null && (
                <span className="ml-3">v{global.version}</span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {dirty && (
                <span className="text-[11px] text-warning">Unsaved changes</span>
              )}
              <button
                onClick={() => void handleSave()}
                disabled={!canSave}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isUpdatingGlobal ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
