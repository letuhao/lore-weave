import { Search, X } from 'lucide-react';
import { inputCls } from './FormBits';

// G-C4: client-side name/code filter box over an already-fetched list. No API call.
export function SearchInput({
  value,
  onChange,
  placeholder = 'Search by name or code…',
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative max-w-xs">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label="Search"
        className={`${inputCls} pl-8 pr-8`}
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:bg-secondary/60"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

// Case-insensitive match over name + code. Empty query matches everything.
export function matchesQuery(query: string, name: string, code: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return name.toLowerCase().includes(q) || code.toLowerCase().includes(q);
}
