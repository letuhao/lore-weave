// 16_chapter_editor_parity_and_retirement.md Phase 2 task 2.11 — the read-only "Original
// source" (untranslated) viewer as a dockable Writing Studio panel. Reproduces
// ChapterEditorPage's legacy "source" tab (lazy-fetch on open, cache once fetched, split into
// numbered paragraphs) as a standalone panel with NO editor coupling — it only fetches and
// renders plain text via booksApi.getOriginalContent.
//
// Params-retargeting singleton ({bookId, chapterId}), same precedent as JsonEditorPanel /
// BookReaderPanel / JobDetailPanel: hiddenFromPalette, opened only via a per-chapter dock id
// (`original-source:{chapterId}`) from EditorPanel's toolbar — never the command palette or an
// agent MCP tool (no MCP tool exists for it).
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';

interface OriginalSourceParams { bookId?: unknown; chapterId?: unknown }

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function OriginalSourcePanel(props: IDockviewPanelProps) {
  // Cross-namespace t (KgGapReportPanel precedent): the "read-only" caption and empty-source
  // message reuse the already-4-locale-translated `editor` namespace keys ChapterEditorPage's
  // legacy source tab uses — no new i18n keys/duplication for those two strings.
  const { t } = useTranslation(['studio', 'editor']);
  const { accessToken } = useAuth();

  // Retarget on EVERY updateParameters (JsonEditorPanel/BookReaderPanel precedent — the event
  // fires on every call, even a same-value repeat).
  const p = (props.params ?? {}) as OriginalSourceParams;
  const [target, setTarget] = useState<{ bookId: string | null; chapterId: string | null }>({
    bookId: str(p.bookId), chapterId: str(p.chapterId),
  });
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const np = (next ?? {}) as OriginalSourceParams;
      setTarget({ bookId: str(np.bookId), chapterId: str(np.chapterId) });
    });
    return () => d?.dispose?.();
  }, [props.api]);

  // Self-title the dock tab.
  useEffect(() => {
    const label = t('panels.original-source.title', { defaultValue: 'Original Source' });
    const suffix = target.chapterId ? ` · ${target.chapterId.slice(0, 8)}` : '';
    props.api.setTitle(`${label}${suffix}`);
  }, [props.api, t, target.chapterId]);

  // Lazy-fetch on open, not eagerly; reset to null when the target changes so the NEXT
  // chapter's fetch isn't skipped by the "already fetched" guard (content !== null).
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setContent(null);
  }, [target.bookId, target.chapterId]);

  useEffect(() => {
    if (!accessToken || !target.bookId || !target.chapterId) return;
    if (content !== null || loading) return;
    setLoading(true);
    booksApi.getOriginalContent(accessToken, target.bookId, target.chapterId)
      .then((text) => setContent(text))
      .catch(() => setContent(''))
      .finally(() => setLoading(false));
  }, [accessToken, target.bookId, target.chapterId, content, loading]);

  if (!target.bookId || !target.chapterId) {
    return (
      <div data-testid="studio-original-source" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('panels.original-source.empty', { defaultValue: 'Open a chapter from the Editor to view its original source.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-original-source" className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex-shrink-0 border-b px-3 py-2 text-[10px] text-muted-foreground">
        {t('original_readonly', { ns: 'editor', defaultValue: 'Original uploaded text — read only' })}
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div data-testid="original-source-loading" className="space-y-2">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-3 w-full" />
          </div>
        ) : content ? (
          <div className="space-y-0">
            {content.split(/\n\n+/).filter(Boolean).map((line, i) => (
              <div key={i} className="flex gap-2 border-b border-border/30 px-3 py-1.5">
                <span className="w-5 flex-shrink-0 text-right font-mono text-[10px] text-muted-foreground/50">{i + 1}</span>
                <p className="text-xs leading-[1.75] text-foreground/70">{line}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[10px] italic text-muted-foreground">
            {t('no_original', { ns: 'editor', defaultValue: 'No original source — this chapter was created directly in the editor (no file was imported).' })}
          </p>
        )}
      </div>
    </div>
  );
}
