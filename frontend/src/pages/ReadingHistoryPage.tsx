import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Clock, ArrowRight } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type ReadingHistoryEntry } from '@/features/books/api';
import { cn } from '@/lib/utils';

type BookGroup = {
  book_id: string;
  book_title: string;
  total_time_ms: number;
  chapters: ReadingHistoryEntry[];
  last_read: string;
};

function groupByBook(entries: ReadingHistoryEntry[]): BookGroup[] {
  const map = new Map<string, BookGroup>();
  for (const e of entries) {
    let g = map.get(e.book_id);
    if (!g) {
      g = { book_id: e.book_id, book_title: e.book_title, total_time_ms: 0, chapters: [], last_read: e.read_at };
      map.set(e.book_id, g);
    }
    g.chapters.push(e);
    g.total_time_ms += e.time_spent_ms;
    if (e.read_at > g.last_read) g.last_read = e.read_at;
  }
  return [...map.values()].sort((a, b) => b.last_read.localeCompare(a.last_read));
}

function formatTime(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  const mins = Math.round(ms / 60_000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

export default function ReadingHistoryPage() {
  const { accessToken } = useAuth();
  const [groups, setGroups] = useState<BookGroup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    booksApi.getReadingHistory(accessToken)
      .then(r => setGroups(groupByBook(r.items)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [accessToken]);

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="space-y-4">
          {[1, 2, 3].map(i => <div key={i} className="h-20 animate-pulse rounded-lg bg-secondary" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="mb-1 text-lg font-semibold">Reading History</h1>
      <p className="mb-6 text-xs text-muted-foreground">Your recently read books and chapters.</p>

      {groups.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <BookOpen className="h-10 w-10 opacity-40" />
          <p className="text-sm">No reading history yet. Start reading a chapter!</p>
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map(g => {
            const lastChapter = g.chapters[0];
            const completion = g.chapters.length > 0
              ? Math.round(g.chapters.filter(c => c.scroll_depth >= 0.9).length / g.chapters.length * 100)
              : 0;
            return (
              <div key={g.book_id} className="rounded-lg border bg-card p-4 transition-colors hover:bg-card-hover">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <Link
                      to={`/books/${g.book_id}`}
                      className="text-sm font-semibold hover:text-primary transition-colors line-clamp-1"
                    >
                      {g.book_title}
                    </Link>
                    <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTime(g.total_time_ms)}
                      </span>
                      <span>{g.chapters.length} {g.chapters.length === 1 ? 'chapter' : 'chapters'} read</span>
                      <span>{completion}% complete</span>
                      <span className="text-muted-foreground/50">
                        Last read {new Date(g.last_read).toLocaleDateString()}
                      </span>
                    </div>
                    {/* Progress bar */}
                    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${completion}%` }}
                      />
                    </div>
                  </div>
                  {/* Continue reading */}
                  {lastChapter && (
                    <Link
                      to={`/books/${g.book_id}/chapters/${lastChapter.chapter_id}/read`}
                      className="flex shrink-0 items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
                    >
                      Continue
                      <ArrowRight className="h-3 w-3" />
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
