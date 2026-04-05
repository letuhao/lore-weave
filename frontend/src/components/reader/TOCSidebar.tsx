import { useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Book, Chapter } from '@/features/books/api';

interface TOCSidebarProps {
  open: boolean;
  onClose: () => void;
  book: Book | null;
  chapters: Chapter[];
  currentChapterId: string;
  currentIdx: number;
  progress: number;
  bookId: string;
}

export function TOCSidebar({
  open,
  onClose,
  book,
  chapters,
  currentChapterId,
  currentIdx,
  progress,
  bookId,
}: TOCSidebarProps) {
  const navigate = useNavigate();

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-30 bg-black/50" onClick={onClose} />
      <div className="fixed bottom-0 left-0 top-0 z-[31] w-80 border-r bg-card shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b p-4">
          <div>
            <h2 className="font-serif text-sm font-semibold">{book?.title}</h2>
            <p className="text-[11px] text-muted-foreground">
              {book?.original_language && <>{book.original_language} &middot; </>}
              {chapters.length} chapters
            </p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Reading progress bar */}
        <div className="flex items-center gap-2.5 border-b px-4 py-3">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <span className="flex-shrink-0 font-mono text-[10px] text-muted-foreground">
            {currentIdx + 1} / {chapters.length}
          </span>
        </div>

        {/* Chapter list */}
        <div className="flex-1 overflow-y-auto">
          {chapters.map((ch, i) => {
            const isCurrent = ch.chapter_id === currentChapterId;
            const isRead = i < currentIdx;
            return (
              <button
                key={ch.chapter_id}
                onClick={() => { navigate(`/books/${bookId}/chapters/${ch.chapter_id}/read`); onClose(); }}
                className={cn(
                  'flex w-full items-center gap-3 border-b px-4 py-2.5 text-left text-xs transition-colors',
                  isCurrent
                    ? 'border-l-2 border-l-primary bg-primary/10 text-primary font-medium'
                    : 'border-l-2 border-l-transparent text-muted-foreground hover:bg-card hover:text-foreground',
                )}
              >
                <span className="w-5 flex-shrink-0 text-right font-mono text-[11px]">{i + 1}</span>
                <span className="flex-1">{ch.title || ch.original_filename}</span>
                {isCurrent && <span className="text-[9px] text-primary">reading</span>}
                {isRead && (
                  <svg className="h-3 w-3 flex-shrink-0 text-success" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" /></svg>
                )}
              </button>
            );
          })}
        </div>

        {/* Footer — language selector added in RD-09 */}
      </div>
    </>
  );
}
