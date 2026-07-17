// SIMPLE MODE (spec docs/specs/2026-07-17-studio-structure-origin; user panel Easy-2/5 fix) — a plain
// linear chapter list, content-first, zero jargon. The word "arc" never appears here. One big door:
// "Write a new chapter" → creates the chapter AND opens the editor (the "just start writing" entry the
// pantser + newcomer both said was missing). Same data model as Advanced — these are real chapters;
// unassigned ones sit in the UnplannedTray until you group them in Advanced.
//
// View-only (React-MVC): it renders; the hook owns the data and the panel owns the actions.
import { useTranslation } from 'react-i18next';
import type { SimpleChapter } from '../hooks/useSimpleChapters';

type Status = 'done' | 'drafting' | 'empty';

/** Map the data we actually have (editorial_status + word_count) to a quiet status. We deliberately
 *  do NOT invent the outline_node status enum here — a chapter list only knows published vs draft and
 *  whether prose exists. Honest and enough for Simple mode. */
function statusOf(c: SimpleChapter): Status {
  if (c.published) return 'done';
  if ((c.word_count ?? 0) > 0) return 'drafting';
  return 'empty';
}

const DOT: Record<Status, string> = {
  done: 'bg-[hsl(var(--success))]',
  drafting: 'bg-primary',
  empty: 'border border-dashed border-muted-foreground/60 bg-transparent',
};

export interface SimpleChapterListProps {
  chapters: SimpleChapter[];
  total: number | null;
  loading: boolean;
  error: boolean;
  hasMore: boolean;
  loadMore: () => void;
  loadingMore: boolean;
  /** Open the chapter in the editor (the studio's manuscript focus). */
  onOpenChapter: (chapterId: string) => void;
  /** Create a new chapter and open it in the editor. Null ⇒ no EDIT grant / no token. */
  onWriteNew: (() => void) | null;
  writing: boolean;
  /** Switch to Advanced (the lane canvas) — used by the empty-state hint. */
  onGoAdvanced: () => void;
}

export function SimpleChapterList({
  chapters, total, loading, error, hasMore, loadMore, loadingMore,
  onOpenChapter, onWriteNew, writing, onGoAdvanced,
}: SimpleChapterListProps) {
  const { t } = useTranslation('studio');

  return (
    <div data-testid="plan-hub-simple" className="flex h-full min-h-0 flex-col">
      {/* plain-language guide — no jargon, tells a newcomer exactly what this is */}
      <p className="border-b border-border/60 bg-accent/[0.04] px-4 py-2.5 text-[12.5px] text-muted-foreground">
        {t('planHub.simple.guide', 'Your book, chapter by chapter. Click one to keep writing, or start a new chapter below.')}
      </p>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && (
          <div data-testid="plan-hub-simple-loading" className="p-6 text-center text-xs text-muted-foreground">
            {t('planHub.simple.loading', 'Loading your chapters…')}
          </div>
        )}
        {error && !loading && (
          <div data-testid="plan-hub-simple-error" className="p-6 text-center text-xs text-destructive">
            {t('planHub.simple.error', "Couldn't load your chapters. Try again in a moment.")}
          </div>
        )}
        {!loading && !error && chapters.length === 0 && (
          <div data-testid="plan-hub-simple-empty" className="flex flex-col items-center gap-3 p-10 text-center">
            <p className="max-w-sm font-serif text-lg italic text-foreground/80">
              {t('planHub.simple.emptyLine', 'A blank book. Start with a sentence — the structure can come later.')}
            </p>
          </div>
        )}

        {!loading && !error && chapters.map((c, i) => {
          const s = statusOf(c);
          return (
            <button
              key={c.chapter_id}
              type="button"
              data-testid={`plan-hub-simple-row-${c.chapter_id}`}
              onClick={() => onOpenChapter(c.chapter_id)}
              className="group flex w-full items-center gap-3 border-b border-border/50 border-l-2 border-l-transparent px-4 py-3 text-left transition-colors hover:border-l-primary/60 hover:bg-secondary/50"
            >
              <span className="w-7 flex-shrink-0 text-right font-mono text-[11px] text-muted-foreground">{i + 1}</span>
              <span className={`h-2 w-2 flex-shrink-0 rounded-full ${DOT[s]}`} />
              <span className="min-w-0 flex-1 truncate font-serif text-[15px] font-semibold text-foreground/95" title={c.title || undefined}>
                {c.title || t('planHub.simple.untitled', 'Untitled chapter')}
              </span>
              <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground">
                {c.word_count != null && c.word_count > 0 ? t('planHub.simple.words', { n: c.word_count.toLocaleString(), defaultValue: '{{n}}w' }) : '—'}
              </span>
              <span className="w-16 flex-shrink-0 text-right font-mono text-[9.5px] uppercase tracking-wide text-muted-foreground">
                {t(`planHub.simple.status.${s}`, s)}
              </span>
              <span className="flex-shrink-0 text-muted-foreground transition-colors group-hover:text-primary">→</span>
            </button>
          );
        })}

        {hasMore && !loading && (
          <button
            type="button"
            data-testid="plan-hub-simple-more"
            onClick={loadMore}
            disabled={loadingMore}
            className="w-full border-b border-border/50 px-4 py-2.5 text-center font-mono text-[11px] text-teal-400/80 hover:text-primary disabled:opacity-50"
          >
            {loadingMore
              ? t('planHub.simple.loadingMore', 'Loading…')
              : t('planHub.simple.more', { n: total != null ? total - chapters.length : '', defaultValue: '+ {{n}} more' })}
          </button>
        )}
      </div>

      {/* the ONE door */}
      <div className="flex-shrink-0 border-t border-border p-4">
        <button
          type="button"
          data-testid="plan-hub-simple-write"
          disabled={!onWriteNew || writing}
          onClick={() => onWriteNew?.()}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-3.5 text-[15px] font-semibold text-primary-foreground transition hover:brightness-105 disabled:opacity-50"
        >
          {writing ? t('planHub.simple.writing', 'Creating…') : `＋  ${t('planHub.simple.writeCta', 'Write a new chapter')}`}
        </button>
        <p className="mt-2 text-center text-[11.5px] text-muted-foreground">
          {t('planHub.simple.doorNote', 'Opens a blank page straight away.')}{' '}
          <button type="button" onClick={onGoAdvanced} className="border-b border-dotted border-accent/50 text-teal-400 hover:text-teal-300">
            {t('planHub.simple.goAdvanced', 'Organise into storylines →')}
          </button>
        </p>
      </div>
    </div>
  );
}
