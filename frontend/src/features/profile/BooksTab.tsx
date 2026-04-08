import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { CatalogBook } from './api';
import { fetchUserBooks } from './api';

type Props = { userId: string };

export function BooksTab({ userId }: Props) {
  const { t } = useTranslation('profile');
  const [books, setBooks] = useState<CatalogBook[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchUserBooks(userId, { limit: 50 })
      .then((res) => {
        setBooks(res.items);
        setTotal(res.total);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) {
    return <div className="py-8 text-center text-sm text-[var(--muted-fg)]">{t('loading')}</div>;
  }

  if (error) {
    return <div className="py-8 text-center text-sm text-[var(--muted-fg)]">{t('loadError')}</div>;
  }

  if (books.length === 0) {
    return <div className="py-8 text-center text-sm text-[var(--muted-fg)]">{t('noBooks')}</div>;
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden bg-[var(--card)]">
      {books.map((book) => (
        <Link
          key={book.book_id}
          to={`/browse/${book.book_id}`}
          className="flex gap-3.5 px-3.5 py-3.5 border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--card-hover)] transition-colors"
        >
          {/* Cover placeholder */}
          <div
            className="w-12 h-[68px] rounded-md flex-shrink-0 border border-[var(--border)]"
            style={{
              background: book.has_cover && book.cover_url
                ? `url(${book.cover_url}) center/cover`
                : 'linear-gradient(135deg, #2d1740, #1a1030)',
            }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="font-serif text-[15px] font-semibold truncate">{book.title}</span>
              {book.genre_tags.map((g) => (
                <span
                  key={g}
                  className="px-1.5 py-px rounded text-[9px] bg-[rgba(139,92,246,0.12)] text-[#c4b5fd]"
                >
                  {g}
                </span>
              ))}
            </div>
            {book.description && (
              <p className="text-xs text-[var(--muted-fg)] leading-relaxed mb-1.5 line-clamp-2">
                {book.description}
              </p>
            )}
            <div className="flex items-center gap-3 text-[11px] text-[var(--muted-fg)]">
              <span>{book.chapter_count} {t('chapters')}</span>
              <span>{book.view_count.toLocaleString()} {t('readers')}</span>
              {book.original_language && (
                <span className="px-1 py-px rounded text-[9px] font-mono bg-[var(--secondary)] text-[var(--muted-fg)]">
                  {book.original_language}
                </span>
              )}
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
