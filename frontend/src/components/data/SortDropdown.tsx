import { cn } from '@/lib/utils';
import { Select } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import type { SortState } from './types';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';

interface SortOption {
  field: string;
  label: string;
}

interface SortDropdownProps {
  sort: SortState | null;
  options: SortOption[];
  onSortChange: (sort: SortState | null) => void;
  className?: string;
}

export function SortDropdown({ sort, options, onSortChange, className }: SortDropdownProps) {
  function handleFieldChange(field: string) {
    if (!field) {
      onSortChange(null);
    } else {
      onSortChange({ field, direction: sort?.direction ?? 'asc' });
    }
  }

  function toggleDirection() {
    if (!sort) return;
    onSortChange({ ...sort, direction: sort.direction === 'asc' ? 'desc' : 'asc' });
  }

  const DirectionIcon = !sort ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown;

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <Select
        value={sort?.field ?? ''}
        onChange={(e) => handleFieldChange(e.target.value)}
        className="h-8 text-xs"
      >
        <option value="">Sort by…</option>
        {options.map((o) => (
          <option key={o.field} value={o.field}>
            {o.label}
          </option>
        ))}
      </Select>
      {sort && (
        <Button
          variant="outline"
          size="sm"
          onClick={toggleDirection}
          className="h-8 w-8 p-0"
          aria-label={`Sort ${sort.direction === 'asc' ? 'ascending' : 'descending'}`}
        >
          <DirectionIcon className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}
