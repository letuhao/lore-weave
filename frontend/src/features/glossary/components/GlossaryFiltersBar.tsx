import type { EntityKind, EntityStatus, FilterState } from '../types';

type Props = {
  filters: FilterState;
  kinds: EntityKind[];
  onChange: (partial: Partial<FilterState>) => void;
};

const STATUS_OPTIONS: { value: 'all' | EntityStatus; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
];

export function GlossaryFiltersBar({ filters, kinds, onChange }: Props) {

  function toggleKind(code: string) {
    const next = filters.kindCodes.includes(code)
      ? filters.kindCodes.filter((c) => c !== code)
      : [...filters.kindCodes, code];
    onChange({ kindCodes: next });
  }

  function toggleUnlinked() {
    onChange({ chapterIds: filters.chapterIds === 'unlinked' ? [] : 'unlinked' });
  }

  const activeChips: { label: string; onRemove: () => void }[] = [];

  if (filters.status !== 'all') {
    activeChips.push({
      label: `Status: ${filters.status}`,
      onRemove: () => onChange({ status: 'all' }),
    });
  }
  if (filters.chapterIds === 'unlinked') {
    activeChips.push({ label: 'Unlinked only', onRemove: () => onChange({ chapterIds: [] }) });
  }
  filters.tags.forEach((tag) =>
    activeChips.push({
      label: `#${tag}`,
      onRemove: () => onChange({ tags: filters.tags.filter((t) => t !== tag) }),
    }),
  );

  function handleTagKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const val = e.currentTarget.value.trim().replace(/,$/, '');
      if (val && !filters.tags.includes(val)) {
        onChange({ tags: [...filters.tags, val] });
      }
      e.currentTarget.value = '';
    }
  }

  return (
    <div className="space-y-3">
      {/* Row 1: search + status + unlinked */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Search entities…"
          value={filters.searchQuery}
          onChange={(e) => onChange({ searchQuery: e.target.value })}
          className="h-8 w-48 rounded border bg-background px-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />

        <select
          value={filters.status}
          onChange={(e) => onChange({ status: e.target.value as 'all' | EntityStatus })}
          className="h-8 rounded border bg-background px-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <button
          onClick={toggleUnlinked}
          className={`h-8 rounded border px-2 text-xs font-medium transition ${
            filters.chapterIds === 'unlinked'
              ? 'border-primary bg-primary text-primary-foreground'
              : 'hover:bg-muted'
          }`}
        >
          Unlinked
        </button>

        {/* Tag input */}
        <input
          type="text"
          placeholder="Add tag filter…"
          onKeyDown={handleTagKeyDown}
          className="h-8 w-36 rounded border bg-background px-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* Row 2: kind chips */}
      {kinds.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {kinds.map((k) => {
            const active = filters.kindCodes.includes(k.code);
            return (
              <button
                key={k.kind_id}
                onClick={() => toggleKind(k.code)}
                className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition"
                style={
                  active
                    ? { borderColor: k.color, backgroundColor: k.color + '22', color: k.color }
                    : { borderColor: k.color + '60', color: k.color + 'aa' }
                }
              >
                {k.icon} {k.name}
              </button>
            );
          })}
        </div>
      )}

      {/* Active filter chips */}
      {activeChips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {activeChips.map((chip) => (
            <span
              key={chip.label}
              className="inline-flex items-center gap-1 rounded-full border bg-muted px-2 py-0.5 text-xs"
            >
              {chip.label}
              <button
                onClick={chip.onRemove}
                className="ml-0.5 hover:text-destructive"
                aria-label={`Remove ${chip.label}`}
              >
                ✕
              </button>
            </span>
          ))}
          <button
            onClick={() =>
              onChange({ kindCodes: [], status: 'all', chapterIds: [], searchQuery: '', tags: [] })
            }
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
