import { useTranslation } from 'react-i18next';
import { Star, Heart } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { LeaderboardBook } from './api';
import { RankMedal } from './RankMedal';
import { TrendArrow } from './TrendArrow';

const GRADIENTS = [
  'from-[#2d1740] to-[#1a1030]',
  'from-[#162824] to-[#0a1a14]',
  'from-[#302018] to-[#1a100c]',
  'from-[#1a1828] to-[#100e20]',
  'from-[#1c2830] to-[#0e1820]',
  'from-[#2a1a18] to-[#1a0e0c]',
  'from-[#201830] to-[#100c20]',
  'from-[#182028] to-[#0c1018]',
];

function hashGradient(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return GRADIENTS[Math.abs(h) % GRADIENTS.length];
}

const genreColors: Record<string, string> = {
  Fantasy: 'bg-purple-500/10 text-purple-300',
  Romance: 'bg-pink-500/10 text-pink-300',
  'Sci-Fi': 'bg-cyan-500/10 text-cyan-300',
  Drama: 'bg-amber-500/10 text-amber-300',
  Historical: 'bg-orange-500/10 text-orange-300',
  Cultivation: 'bg-yellow-500/10 text-yellow-300',
  Isekai: 'bg-green-500/10 text-green-300',
};

export function RankingList({
  books,
  sort,
  onSortChange,
  hasMore,
  onLoadMore,
  loading,
}: {
  books: LeaderboardBook[];
  sort: string;
  onSortChange: (s: string) => void;
  hasMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
}) {
  const { t } = useTranslation('leaderboard');

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <span className="text-xs font-semibold">{t('ranking.fullRankings')}</span>
        <div className="flex gap-1">
          {(['rating', 'readers', 'favorites'] as const).map((s) => (
            <button
              key={s}
              onClick={() => onSortChange(s)}
              className={cn(
                'rounded px-2 py-1 text-[10px] font-medium transition-colors',
                sort === s ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`ranking.${s}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Rows */}
      {books.map((book) => (
        <div
          key={book.book_id}
          className={cn(
            'flex items-center gap-3.5 border-b px-4 py-3 transition-colors last:border-b-0 hover:bg-card/80',
            book.rank === 1 && 'border-l-2 border-l-primary bg-primary/5',
          )}
        >
          <RankMedal rank={book.rank} />

          {/* Cover mini */}
          <div
            className={`h-[46px] w-8 shrink-0 overflow-hidden rounded border bg-gradient-to-br ${hashGradient(book.book_id)}`}
          >
            {book.has_cover && (
              <img
                src={`/v1/books/${book.book_id}/cover`}
                alt=""
                className="h-full w-full object-cover"
                loading="lazy"
              />
            )}
          </div>

          {/* Info */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="truncate font-serif text-[13px] font-semibold">{book.title}</span>
              {book.genre_tags[0] && (
                <span
                  className={cn(
                    'shrink-0 rounded px-1.5 py-px text-[9px] font-medium',
                    genreColors[book.genre_tags[0]] ?? 'bg-secondary text-muted-foreground',
                  )}
                >
                  {book.genre_tags[0]}
                </span>
              )}
              {book.original_language && (
                <span className="shrink-0 rounded bg-secondary px-1.5 py-px text-[9px] text-muted-foreground">
                  {book.original_language}
                </span>
              )}
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>by {book.owner_display_name || 'Unknown'}</span>
              <span className="text-border">&middot;</span>
              <span>{book.chapter_count} {t('ranking.chapters')}</span>
              {book.translation_count > 0 && (
                <>
                  <span className="text-border">&middot;</span>
                  <span>{book.translation_count} {t('ranking.translations')}</span>
                </>
              )}
            </div>
          </div>

          {/* Stats */}
          <div className="flex shrink-0 items-center gap-4">
            <div className="text-center">
              <div className="flex items-center gap-0.5">
                <Star className="h-3 w-3 fill-primary text-primary" />
                <span className="text-sm font-bold">{book.avg_rating.toFixed(1)}</span>
              </div>
              <span className="text-[9px] text-muted-foreground">
                {book.rating_count} {t('ranking.ratings')}
              </span>
            </div>

            <div className="text-center">
              <span className="text-sm font-semibold text-[#e85d75]">{book.favorites_count}</span>
              <Heart className="ml-0.5 inline-block h-2.5 w-2.5 fill-[#e85d75] text-[#e85d75]" style={{ verticalAlign: '-1px' }} />
              <br />
              <span className="text-[9px] text-muted-foreground">{t('ranking.favorites')}</span>
            </div>

            <div className="text-center">
              <span className="text-sm font-semibold">{formatCount(book.unique_readers)}</span>
              <br />
              <span className="text-[9px] text-muted-foreground">{t('ranking.readers')}</span>
            </div>

            <TrendArrow change={book.rank_change} />
          </div>
        </div>
      ))}

      {/* Load more */}
      {hasMore && (
        <div className="border-t p-3 text-center">
          <button
            onClick={onLoadMore}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
          >
            {t('ranking.showMore')}
          </button>
        </div>
      )}
    </div>
  );
}

function formatCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
