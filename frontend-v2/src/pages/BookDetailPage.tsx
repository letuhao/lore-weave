import { useEffect, useState } from 'react';
import { Link, useParams, useLocation, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Settings, Plus, Trash2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { PageHeader } from '@/components/layout/PageHeader';
import { StatusBadge, Skeleton, ConfirmDialog } from '@/components/shared';
import { LanguageDisplay } from '@/components/shared/LanguageDisplay';
import { cn } from '@/lib/utils';

const tabs = [
  { key: '', label: 'Chapters' },
  { key: '/translation', label: 'Translation' },
  { key: '/glossary', label: 'Glossary' },
  { key: '/wiki', label: 'Wiki' },
  { key: '/sharing', label: 'Sharing' },
  { key: '/settings', label: 'Settings' },
];

export function BookDetailPage() {
  const { bookId = '' } = useParams();
  const { accessToken } = useAuth();
  const { t } = useTranslation('books');
  const location = useLocation();
  const [book, setBook] = useState<Book | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [trashOpen, setTrashOpen] = useState(false);

  useEffect(() => {
    if (!accessToken || !bookId) return;
    setLoading(true);
    booksApi.getBook(accessToken, bookId)
      .then((b) => { setBook(b); setError(''); })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [accessToken, bookId]);

  const handleTrash = async () => {
    if (!accessToken || !bookId) return;
    await booksApi.trashBook(accessToken, bookId);
    window.location.href = '/books';
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (error || !book) {
    return <p className="text-sm text-destructive">{error || 'Book not found'}</p>;
  }

  // Determine active tab from URL
  const basePath = `/books/${bookId}`;
  const suffix = location.pathname.replace(basePath, '') || '';

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: t('workspace'), to: '/books' },
          { label: book.title },
        ]}
        title={book.title}
        subtitle={
          <span className="flex items-center gap-2">
            {book.original_language && <LanguageDisplay code={book.original_language} />}
            <span className="text-border">·</span>
            <span>{t('card.chapters', { count: book.chapter_count })}</span>
            {book.updated_at && (
              <>
                <span className="text-border">·</span>
                <span>Updated {new Date(book.updated_at).toLocaleDateString()}</span>
              </>
            )}
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            {book.visibility && <StatusBadge variant={book.visibility} />}
            <button
              onClick={() => setTrashOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <Link
              to={`/books/${bookId}/settings`}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Settings className="h-3.5 w-3.5" />
            </Link>
          </div>
        }
        tabs={
          <div className="flex gap-1 border-b -mx-6 px-6 lg:-mx-10 lg:px-10">
            {tabs.map((tab) => (
              <Link
                key={tab.key}
                to={`${basePath}${tab.key}`}
                className={cn(
                  'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                  suffix === tab.key
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {tab.label}
              </Link>
            ))}
          </div>
        }
      />

      {/* Tab content — render inline based on URL */}
      <BookTabContent bookId={bookId} book={book} activeTab={suffix} onReload={() => {
        if (accessToken) booksApi.getBook(accessToken, bookId).then(setBook).catch(() => {});
      }} />

      <ConfirmDialog
        open={trashOpen}
        onOpenChange={setTrashOpen}
        title="Move to trash?"
        description={`"${book.title}" and all chapters will be moved to trash. You can restore within 30 days.`}
        confirmLabel="Move to Trash"
        variant="destructive"
        onConfirm={() => void handleTrash()}
      />
    </div>
  );
}

function BookTabContent({ bookId, book, activeTab, onReload }: {
  bookId: string; book: Book; activeTab: string; onReload: () => void;
}) {
  // For now, show placeholder for tabs we haven't built yet
  const placeholders: Record<string, string> = {
    '/translation': 'Translation matrix — coming in P3-01.',
    '/glossary': 'Glossary management — coming in P3-05.',
    '/wiki': 'Wiki — coming in P3-17.',
    '/sharing': 'Sharing settings — coming in P3-20.',
    '/settings': 'Book settings — coming in P3-21.',
  };

  if (activeTab === '') {
    return <ChaptersTabPlaceholder bookId={bookId} />;
  }

  return (
    <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
      {placeholders[activeTab] ?? 'Unknown tab'}
    </div>
  );
}

function ChaptersTabPlaceholder({ bookId }: { bookId: string }) {
  return (
    <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
      Chapters DataTable — coming in P2-04.
    </div>
  );
}
