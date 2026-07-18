// Simple mode — ONE chapter row. Content-first: click to open in the editor. Rename (inline) + delete
// are the CRUD the panel asked for, shown on hover so the row stays calm. Authorship codes quietly:
// a writer's chapter is Lora serif; an AI-proposed one is Mono + a teal "AI idea" tag (the panel's
// unanimous keep). Status is one quiet dot + a word — no chips.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { SimpleChapter } from '../hooks/useSimpleChapters';

type Status = 'done' | 'drafting' | 'empty';

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

export interface SimpleChapterRowProps {
  chapter: SimpleChapter;
  index: number;
  onOpen: (chapterId: string) => void;
  onRename: ((chapterId: string, title: string) => void) | null;
  onDelete: ((chapterId: string) => void) | null;
  busy: boolean;
}

export function SimpleChapterRow({ chapter: c, index, onOpen, onRename, onDelete, busy }: SimpleChapterRowProps) {
  const { t } = useTranslation('studio');
  const s = statusOf(c);
  const machine = c.source === 'mined';
  // Same display rule as the manuscript navigator (chapterDisplayTitle): a named chapter shows its
  // title; an unnamed one shows "Chapter {n}" — never the storage filename (F4). One rule, both surfaces.
  const displayTitle = c.title?.trim()
    ? c.title
    : t('manuscript.chapterN', { number: c.sort_order, defaultValue: 'Chapter {{number}}' });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (onRename && next && next !== c.title) onRename(c.chapter_id, next);
    else setDraft(c.title);
  };

  return (
    <div
      data-testid={`plan-hub-simple-row-${c.chapter_id}`}
      data-status={s}
      data-source={c.source}
      className="group flex items-center gap-3 border-b border-border/50 border-l-2 border-l-transparent px-4 py-3 transition-colors hover:border-l-primary/60 hover:bg-secondary/50"
    >
      <span className="w-7 flex-shrink-0 text-right font-mono text-[11px] text-muted-foreground">{index + 1}</span>
      <span className={cn('h-2 w-2 flex-shrink-0 rounded-full', DOT[s])} />

      {editing ? (
        <input
          ref={inputRef}
          data-testid={`plan-hub-simple-rename-${c.chapter_id}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            else if (e.key === 'Escape') { setDraft(c.title); setEditing(false); }
          }}
          className="min-w-0 flex-1 rounded border bg-background px-1.5 py-0.5 font-serif text-[15px]"
        />
      ) : (
        <button
          type="button"
          onClick={() => onOpen(c.chapter_id)}
          className={cn(
            'min-w-0 flex-1 truncate text-left font-semibold text-foreground/95',
            machine ? 'font-mono text-[13px] text-foreground/85' : 'font-serif text-[15px]',
          )}
          title={displayTitle}
        >
          {displayTitle}
        </button>
      )}

      <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground">
        {c.word_count != null && c.word_count > 0 ? t('planHub.simple.words', { n: c.word_count.toLocaleString(), defaultValue: '{{n}}w' }) : '—'}
      </span>
      <span className={cn('w-16 flex-shrink-0 text-right font-mono text-[9.5px] uppercase tracking-wide', machine ? 'text-teal-400' : 'text-muted-foreground')}>
        {machine ? t('planHub.simple.status.aiIdea', 'AI idea') : t(`planHub.simple.status.${s}`, s)}
      </span>

      {/* CRUD — calm until hover. Rename + delete were the gap the panel named ("only add and view"). */}
      <span className="flex flex-shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        {onRename && !editing && (
          <button
            type="button"
            data-testid={`plan-hub-simple-edit-${c.chapter_id}`}
            onClick={() => { setDraft(c.title); setEditing(true); }}
            title={t('planHub.simple.rename', 'Rename')}
            className="rounded px-1 text-muted-foreground hover:text-primary"
          >
            ✎
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            data-testid={`plan-hub-simple-delete-${c.chapter_id}`}
            disabled={busy}
            onClick={() => onDelete(c.chapter_id)}
            title={t('planHub.simple.delete', 'Delete chapter')}
            className="rounded px-1 text-muted-foreground hover:text-destructive disabled:opacity-50"
          >
            🗑
          </button>
        )}
      </span>
      <span className="flex-shrink-0 text-muted-foreground transition-colors group-hover:text-primary">→</span>
    </div>
  );
}
