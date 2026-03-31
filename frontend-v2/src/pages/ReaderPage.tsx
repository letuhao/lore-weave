import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { Menu, X, ChevronLeft, ChevronRight, Sun, Pencil } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { ChapterReadView } from '@/components/shared/ChapterReadView';
import { cn } from '@/lib/utils';

export function ReaderPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [body, setBody] = useState('');
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [book, setBook] = useState<Book | null>(null);
  const [tocOpen, setTocOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    Promise.all([
      booksApi.getBook(accessToken, bookId),
      booksApi.getDraft(accessToken, bookId, chapterId),
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }),
    ]).then(([b, d, chs]) => {
      setBook(b);
      setBody(d.body);
      setChapter(chs.items.find((c) => c.chapter_id === chapterId) ?? null);
      setChapters(chs.items);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [accessToken, bookId, chapterId]);

  const currentIdx = chapters.findIndex((c) => c.chapter_id === chapterId);
  const prevCh = currentIdx > 0 ? chapters[currentIdx - 1] : null;
  const nextCh = currentIdx < chapters.length - 1 ? chapters[currentIdx + 1] : null;
  const progress = chapters.length > 0 ? ((currentIdx + 1) / chapters.length) * 100 : 0;

  if (loading) return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading...</div>;

  return (
    <div className="relative flex h-screen flex-col bg-background">
      {/* Progress bar */}
      <div className="absolute left-0 right-0 top-0 z-20 h-0.5 bg-secondary">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

      {/* Top bar */}
      <div className="flex h-12 flex-shrink-0 items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <button onClick={() => setTocOpen(true)} className="rounded p-1.5 text-muted-foreground hover:bg-secondary">
            <Menu className="h-4 w-4" />
          </button>
          <span className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{book?.title}</span>
            <span className="mx-1.5 text-border">/</span>
            Ch. {currentIdx + 1} of {chapters.length}
          </span>
        </div>
        <div className="flex gap-1">
          {accessToken && (
            <Link to={`/books/${bookId}/chapters/${chapterId}/edit`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Edit">
              <Pencil className="h-4 w-4" />
            </Link>
          )}
          <Link to={`/books/${bookId}`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Back to book">
            <X className="h-4 w-4" />
          </Link>
        </div>
      </div>

      {/* TOC overlay */}
      {tocOpen && (
        <>
          <div className="fixed inset-0 z-30 bg-black/50" onClick={() => setTocOpen(false)} />
          <div className="fixed bottom-0 left-0 top-0 z-31 w-80 border-r bg-card shadow-xl">
            <div className="flex items-center justify-between border-b p-4">
              <div>
                <h2 className="font-serif text-sm font-semibold">{book?.title}</h2>
                <p className="text-xs text-muted-foreground">{chapters.length} chapters</p>
              </div>
              <button onClick={() => setTocOpen(false)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 60px)' }}>
              {chapters.map((ch, i) => (
                <button
                  key={ch.chapter_id}
                  onClick={() => { navigate(`/books/${bookId}/chapters/${ch.chapter_id}/read`); setTocOpen(false); }}
                  className={cn(
                    'flex w-full items-center gap-3 border-b px-4 py-3 text-left text-xs transition-colors',
                    ch.chapter_id === chapterId ? 'border-l-2 border-l-primary bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-card hover:text-foreground',
                  )}
                >
                  <span className="w-5 text-right font-mono">{i + 1}</span>
                  <span className="flex-1">{ch.title || ch.original_filename}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Reading area */}
      <div className="flex flex-1 justify-center overflow-y-auto px-6 py-10">
        <ChapterReadView
          body={body}
          title={chapter?.title || chapter?.original_filename}
          chapterNumber={currentIdx + 1}
        />
      </div>

      {/* Bottom nav */}
      <div className="flex h-14 flex-shrink-0 items-center justify-between border-t px-6">
        {prevCh ? (
          <Link to={`/books/${bookId}/chapters/${prevCh.chapter_id}/read`} className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-xs transition-colors hover:bg-secondary">
            <ChevronLeft className="h-3.5 w-3.5" /> {prevCh.title || `Ch. ${currentIdx}`}
          </Link>
        ) : <div />}
        <span className="text-[10px] text-muted-foreground">Ch. {currentIdx + 1} / {chapters.length}</span>
        {nextCh ? (
          <Link to={`/books/${bookId}/chapters/${nextCh.chapter_id}/read`} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90">
            {nextCh.title || `Ch. ${currentIdx + 2}`} <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        ) : <div />}
      </div>
    </div>
  );
}
