// SIMPLE MODE (spec docs/specs/2026-07-17-studio-structure-origin; user panel Easy-2/5 fix) — a plain
// linear chapter list, content-first, zero jargon. The word "arc" never appears here. One big door:
// "Write a new chapter" → creates the chapter AND opens the editor (the "just start writing" entry the
// pantser + newcomer both said was missing). Same data model as Advanced — these are real chapters;
// unassigned ones sit in the UnplannedTray until you group them in Advanced.
//
// View-only (React-MVC): it renders; the hook owns the data and the panel owns the actions.
import { useTranslation } from 'react-i18next';
import type { SimpleChapter } from '../hooks/useSimpleChapters';
import { SimpleChapterRow } from './SimpleChapterRow';

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
  /** Rename a chapter (inline). Null ⇒ no EDIT grant. */
  onRename: ((chapterId: string, title: string) => void) | null;
  /** Delete (trash) a chapter. Null ⇒ no EDIT grant. */
  onDelete: ((chapterId: string) => void) | null;
  /** A rename/delete is in flight. */
  mutating: boolean;
  /** "Or let the AI draft one" — open the planner/co-writer. Null ⇒ unavailable. */
  onAiDraft: (() => void) | null;
  /** Switch to Advanced (the lane canvas) — used by the guide + empty-state hint. */
  onGoAdvanced: () => void;
}

export function SimpleChapterList({
  chapters, total, loading, error, hasMore, loadMore, loadingMore,
  onOpenChapter, onWriteNew, writing, onRename, onDelete, mutating, onAiDraft, onGoAdvanced,
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

        {!loading && !error && chapters.map((c, i) => (
          <SimpleChapterRow
            key={c.chapter_id}
            chapter={c}
            index={i}
            onOpen={onOpenChapter}
            onRename={onRename}
            onDelete={onDelete}
            busy={mutating}
          />
        ))}

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

      {/* legend — the quiet key to the type/colour coding (authorship) + the status dots. */}
      <div data-testid="plan-hub-simple-legend" className="flex flex-shrink-0 flex-wrap gap-x-4 gap-y-1 border-t border-border/60 px-4 py-2 text-[10.5px] text-muted-foreground">
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full align-[-1px]" style={{ background: 'hsl(35 85% 55% / .85)' }} />{t('planHub.simple.legend.authored', 'you wrote it')}</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full align-[-1px]" style={{ background: 'hsl(170 40% 45% / .85)' }} />{t('planHub.simple.legend.ai', 'AI idea')}</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[hsl(var(--success))] align-[-1px]" />{t('planHub.simple.status.done', 'done')}</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-primary align-[-1px]" />{t('planHub.simple.status.drafting', 'drafting')}</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full border border-dashed border-muted-foreground/60 align-[-1px]" />{t('planHub.simple.status.empty', 'not started')}</span>
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
          {onAiDraft && (
            <button
              type="button"
              data-testid="plan-hub-simple-ai-draft"
              onClick={onAiDraft}
              className="border-b border-dotted border-accent/50 text-teal-400 hover:text-teal-300"
            >
              {t('planHub.simple.aiDraft', 'Or let the AI draft one →')}
            </button>
          )}
        </p>
        <p className="mt-1 text-center text-[11px] text-muted-foreground/80">
          <button type="button" data-testid="plan-hub-simple-more-advanced" onClick={onGoAdvanced} className="border-b border-dotted border-accent/40 text-teal-400/80 hover:text-teal-300">
            {t('planHub.simple.goAdvanced', 'Organise into storylines →')}
          </button>
        </p>
      </div>
    </div>
  );
}
