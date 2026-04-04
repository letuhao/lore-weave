import { Link } from 'react-router-dom';

// Deterministic gradient from book_id hash
const GRADIENTS = [
  'from-[#2d1740] to-[#1a1030]', // purple
  'from-[#162824] to-[#0a1a14]', // green
  'from-[#302018] to-[#1a100c]', // amber
  'from-[#1a1828] to-[#100e20]', // indigo
  'from-[#1c2830] to-[#0e1820]', // cyan
  'from-[#2a1a18] to-[#1a0e0c]', // orange
  'from-[#201830] to-[#100c20]', // violet
  'from-[#182028] to-[#0c1018]', // slate
];

function hashIndex(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return Math.abs(h) % GRADIENTS.length;
}

type Props = {
  book: {
    book_id: string;
    title: string;
    description?: string | null;
    original_language?: string | null;
    summary_excerpt?: string | null;
    chapter_count?: number;
    has_cover?: boolean;
    cover_url?: string | null;
    genre_tags?: string[];
    created_at?: string | null;
  };
};

export function BookCard({ book }: Props) {
  const gradient = GRADIENTS[hashIndex(book.book_id)];
  const lang = book.original_language;

  return (
    <Link
      to={`/browse/${book.book_id}`}
      className="group overflow-hidden rounded-[10px] border bg-card transition-all duration-200 hover:-translate-y-0.5 hover:border-border/80 hover:shadow-[0_8px_24px_rgba(0,0,0,0.3)]"
    >
      {/* Cover */}
      <div className={`relative aspect-[2/3] bg-gradient-to-br ${gradient}`}>
        {book.has_cover && book.cover_url ? (
          <img
            src={book.cover_url}
            alt={book.title}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
          />
        ) : null}
        {/* Gradient overlay */}
        <div className="absolute bottom-0 left-0 right-0 h-3/5 bg-gradient-to-t from-black/70 to-transparent" />
        {/* Genre pills */}
        {book.genre_tags && book.genre_tags.length > 0 && (
          <div className="absolute bottom-2 left-2 flex flex-wrap gap-1">
            {book.genre_tags.slice(0, 3).map((g) => (
              <span
                key={g}
                className="rounded px-1.5 py-px text-[9px] font-medium"
                style={{ background: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.85)' }}
              >
                {g}
              </span>
            ))}
            {book.genre_tags.length > 3 && (
              <span className="rounded px-1.5 py-px text-[9px] font-medium" style={{ background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.6)' }}>
                +{book.genre_tags.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="px-3.5 py-3">
        <h3 className="line-clamp-2 font-serif text-sm font-semibold leading-snug">
          {book.title}
        </h3>
        {book.summary_excerpt && (
          <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
            {book.summary_excerpt}
          </p>
        )}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            {book.chapter_count ?? 0} chapters
          </span>
          {lang && (
            <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
              {lang}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
