import { Star } from 'lucide-react';
import type { LeaderboardBook } from './api';
import { TrendArrow } from './TrendArrow';

const GRADIENTS = [
  'from-[#2d1740] to-[#1a1030]',
  'from-[#162824] to-[#0a1a14]',
  'from-[#302018] to-[#1a100c]',
];

function hashGradient(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return GRADIENTS[Math.abs(h) % GRADIENTS.length];
}

const barConfig = [
  { height: 80, border: 'var(--silver, #b0b0b0)', color: '#b0b0b0', size: 52, fontSize: 20 },
  { height: 110, border: 'var(--gold, #e8a832)', color: '#e8a832', size: 60, fontSize: 24 },
  { height: 60, border: 'var(--bronze, #cd7f32)', color: '#cd7f32', size: 52, fontSize: 20 },
];

// Podium renders top 3 books in order: #2 (left), #1 (center), #3 (right)
export function Podium({ books }: { books: LeaderboardBook[] }) {
  if (books.length < 3) return null;

  const order = [books[1], books[0], books[2]]; // silver, gold, bronze

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-end justify-center gap-2 pt-6">
        {order.map((book, i) => {
          const cfg = barConfig[i];
          const gradient = hashGradient(book.book_id);
          const initials = book.title
            .split(/\s+/)
            .slice(0, 2)
            .map((w) => w[0])
            .join('')
            .toUpperCase();

          return (
            <div key={book.book_id} className="flex flex-col items-center">
              {/* Avatar */}
              <div
                className={`flex items-center justify-center rounded-full bg-gradient-to-br ${gradient} -mb-[30px]`}
                style={{
                  width: cfg.size,
                  height: cfg.size,
                  border: `3px solid ${cfg.border}`,
                }}
              >
                <span className="font-serif text-[9px] text-muted-foreground">{initials}</span>
              </div>

              {/* Title + author */}
              <span
                className="mt-10 text-center font-semibold"
                style={{ fontSize: i === 1 ? 14 : 12 }}
              >
                {book.title}
              </span>
              <span className="text-[10px] text-muted-foreground">
                by {book.owner_display_name || 'Unknown'}
              </span>

              {/* Rating */}
              <div className="mt-1 flex items-center gap-0.5">
                <Star className="h-3 w-3 fill-primary text-primary" />
                <span className="text-xs font-semibold">{book.avg_rating.toFixed(1)}</span>
                {i === 1 && book.rank_change !== 0 && (
                  <span className="ml-1">
                    <TrendArrow change={book.rank_change} />
                  </span>
                )}
              </div>

              {/* Podium bar */}
              <div
                className="mt-2 flex w-[120px] flex-col items-center rounded-t-lg pt-4"
                style={{
                  height: cfg.height,
                  background: `linear-gradient(180deg, ${cfg.color}15, ${cfg.color}05)`,
                  ...(i === 1 ? { border: `1px solid ${cfg.color}26`, borderBottom: 'none' } : {}),
                }}
              >
                <span className="font-bold" style={{ fontSize: cfg.fontSize, color: cfg.color }}>
                  {book.rank}
                </span>
                <span className="mt-1 text-[10px] text-muted-foreground">
                  {formatCount(book.unique_readers)} readers
                </span>
                {i === 1 && book.favorites_count > 0 && (
                  <span className="mt-0.5 text-[9px] text-primary">
                    {book.favorites_count} favorites
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
