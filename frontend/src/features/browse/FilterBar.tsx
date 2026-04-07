import { cn } from '@/lib/utils';

const LANGUAGES = [
  { code: '', label: 'All' },
  { code: 'ja', label: '日本語 (ja)' },
  { code: 'en', label: 'English (en)' },
  { code: 'vi', label: 'Tiếng Việt (vi)' },
  { code: 'zh-TW', label: '繁體中文 (zh-TW)' },
  { code: 'ko', label: '한국어 (ko)' },
];

const SORTS = [
  { value: 'recent', label: 'Most recent' },
  { value: 'popular', label: 'Most popular' },
  { value: 'chapters', label: 'Most chapters' },
  { value: 'alpha', label: 'Alphabetical' },
];

// Deterministic color from genre name hash (no genre_groups lookup needed)
const GENRE_COLORS = [
  '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#3dba6a',
  '#e8a832', '#dc4e4e', '#a855f7', '#64748b', '#8b5e3c',
];

function genreColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return GENRE_COLORS[Math.abs(h) % GENRE_COLORS.length];
}

type Props = {
  language: string;
  genres: string[];
  availableGenres: string[];
  sort: string;
  total: number;
  onLanguageChange: (lang: string) => void;
  onGenreToggle: (genre: string) => void;
  onGenreClear: () => void;
  onSortChange: (sort: string) => void;
};

export function FilterBar({
  language, genres, availableGenres, sort, total,
  onLanguageChange, onGenreToggle, onGenreClear, onSortChange,
}: Props) {
  return (
    <div>
      {/* Filter chips */}
      <div className="mb-4 flex flex-wrap items-center justify-center gap-1.5">
        {/* Language chips */}
        {LANGUAGES.map((l) => (
          <button
            key={l.code}
            onClick={() => onLanguageChange(l.code)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs transition-colors',
              language === l.code
                ? 'border-primary bg-primary/10 text-primary'
                : 'text-muted-foreground hover:border-border/80 hover:text-foreground',
            )}
          >
            {l.label}
          </button>
        ))}

        {/* Separator */}
        {availableGenres.length > 0 && (
          <>
            <span className="mx-1 text-border">|</span>

            {/* Clear genre filter */}
            {genres.length > 0 && (
              <button
                onClick={onGenreClear}
                className="rounded-full border border-dashed px-2.5 py-1 text-[10px] text-muted-foreground hover:border-border/80 hover:text-foreground transition-colors"
              >
                Clear genres
              </button>
            )}
          </>
        )}

        {/* Genre chips (dynamic, multi-select) */}
        {availableGenres.map((g) => {
          const color = genreColor(g);
          const isActive = genres.includes(g);
          return (
            <button
              key={g}
              onClick={() => onGenreToggle(g)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors',
                isActive
                  ? 'text-foreground'
                  : 'text-muted-foreground hover:border-border/80 hover:text-foreground',
              )}
              style={isActive ? { borderColor: color, background: color + '18', color } : undefined}
            >
              <span className="h-1.5 w-1.5 rounded-sm" style={{ background: color }} />
              {g}
            </button>
          );
        })}
      </div>

      {/* Results count + sort */}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13px] text-muted-foreground">
          {total} book{total !== 1 ? 's' : ''} found
          {genres.length > 0 && (
            <> &middot; {genres.map((g, i) => (
              <span key={g}>
                {i > 0 && ' + '}
                <strong style={{ color: genreColor(g) }}>{g}</strong>
              </span>
            ))}</>
          )}
          {language && (
            <> {genres.length > 0 ? '+ ' : '· '}<strong className="text-foreground">{language}</strong></>
          )}
        </span>
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value)}
          aria-label="Sort books by"
          className="h-8 rounded-md border bg-background px-2.5 text-xs"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
