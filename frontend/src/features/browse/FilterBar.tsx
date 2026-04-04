import { cn } from '@/lib/utils';

const LANGUAGES = [
  { code: '', label: 'All' },
  { code: 'ja', label: '日本語 (ja)' },
  { code: 'en', label: 'English (en)' },
  { code: 'vi', label: 'Tiếng Việt (vi)' },
  { code: 'zh-TW', label: '繁體中文 (zh-TW)' },
  { code: 'ko', label: '한국어 (ko)' },
];

const GENRES = ['Fantasy', 'Drama', 'Romance', 'Sci-Fi', 'Historical'];

const SORTS = [
  { value: 'recent', label: 'Most recent' },
  { value: 'chapters', label: 'Most chapters' },
  { value: 'alpha', label: 'Alphabetical' },
];

type Props = {
  language: string;
  sort: string;
  total: number;
  onLanguageChange: (lang: string) => void;
  onSortChange: (sort: string) => void;
};

export function FilterBar({ language, sort, total, onLanguageChange, onSortChange }: Props) {
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

        {/* Genre chips — disabled, deferred to P3-08c */}
        <span className="mx-1 text-border">|</span>
        {GENRES.map((g) => (
          <button
            key={g}
            disabled
            title="Genre filter coming in P3-08c"
            className="cursor-not-allowed rounded-full border border-dashed px-3 py-1 text-xs text-muted-foreground/50"
          >
            {g}
          </button>
        ))}
      </div>

      {/* Results count + sort */}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13px] text-muted-foreground">{total} books found</span>
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
