import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { X, Search, SlidersHorizontal } from 'lucide-react';
import { useState, type ReactNode } from 'react';

/* ── Filter Chip ──────────────────────────────────────────────────────────────── */

interface FilterChipProps {
  label: string;
  onRemove: () => void;
}

export function FilterChip({ label, onRemove }: FilterChipProps) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border bg-muted px-2 py-0.5 text-xs font-medium">
      {label}
      <button
        onClick={onRemove}
        className="ml-0.5 rounded-full p-0.5 hover:bg-background hover:text-destructive"
        aria-label={`Remove filter: ${label}`}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

/* ── Toggle Chip (for kind/category filters) ──────────────────────────────────── */

interface ToggleChipProps {
  label: string;
  icon?: string;
  color?: string;
  active: boolean;
  onToggle: () => void;
}

export function ToggleChip({ label, icon, color, active, onToggle }: ToggleChipProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors"
      style={
        active
          ? { borderColor: color, backgroundColor: (color ?? '') + '22', color }
          : { borderColor: (color ?? '') + '60', color: (color ?? '') + 'aa' }
      }
    >
      {icon && <span>{icon}</span>}
      {label}
    </button>
  );
}

/* ── Tag Input ────────────────────────────────────────────────────────────────── */

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export function TagInput({ tags, onChange, placeholder = 'Add tag…' }: TagInputProps) {
  const [value, setValue] = useState('');

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const tag = value.trim().replace(/,$/, '');
      if (tag && !tags.includes(tag)) {
        onChange([...tags, tag]);
      }
      setValue('');
    }
    if (e.key === 'Backspace' && !value && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border bg-background px-2 py-1">
      {tags.map((tag) => (
        <FilterChip
          key={tag}
          label={`#${tag}`}
          onRemove={() => onChange(tags.filter((t) => t !== tag))}
        />
      ))}
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={tags.length === 0 ? placeholder : ''}
        className="min-w-[80px] flex-1 bg-transparent py-0.5 text-xs outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}

/* ── Filter Toolbar ───────────────────────────────────────────────────────────── */

interface FilterToolbarProps {
  /** Search input value. */
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  /** Active filter chips to display beneath the toolbar. */
  activeFilters?: FilterChipProps[];
  /** Called when "Clear all" is clicked. */
  onClearAll?: () => void;
  /** Slot for additional filter controls (dropdowns, toggles, etc.). */
  children?: ReactNode;
  /** Advanced / collapsible filter section. */
  advancedFilters?: ReactNode;
  className?: string;
}

export function FilterToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search…',
  activeFilters = [],
  onClearAll,
  children,
  advancedFilters,
  className,
}: FilterToolbarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <div className={cn('space-y-2', className)}>
      {/* Row 1: search + filter controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="h-8 w-48 pl-8 text-xs"
          />
        </div>

        {children}

        {advancedFilters && (
          <Button
            variant={showAdvanced ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => setShowAdvanced((s) => !s)}
            className="h-8 text-xs"
          >
            <SlidersHorizontal className="mr-1.5 h-3.5 w-3.5" />
            Filters
          </Button>
        )}
      </div>

      {/* Advanced filters (collapsible) */}
      {showAdvanced && advancedFilters && (
        <div className="rounded-md border bg-muted/30 p-3">{advancedFilters}</div>
      )}

      {/* Active filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {activeFilters.map((chip) => (
            <FilterChip key={chip.label} {...chip} />
          ))}
          {onClearAll && (
            <button
              onClick={onClearAll}
              className="ml-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Clear all
            </button>
          )}
        </div>
      )}
    </div>
  );
}
