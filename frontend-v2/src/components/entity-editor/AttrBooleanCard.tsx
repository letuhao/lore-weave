import type { AttrFieldProps } from './AttrTextCard';
import { cn } from '@/lib/utils';

export function AttrBooleanCard({ value, onChange }: AttrFieldProps) {
  const isOn = value === 'true';
  return (
    <div className="flex items-center gap-2.5">
      <button
        type="button"
        onClick={() => onChange(isOn ? 'false' : 'true')}
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          isOn ? 'bg-success' : 'border bg-secondary',
        )}
      >
        <span className={cn(
          'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-[left]',
          isOn ? 'left-[18px]' : 'left-0.5',
        )} />
      </button>
      <span className={cn('text-xs', isOn ? 'text-success' : 'text-muted-foreground')}>
        {isOn ? 'Yes' : 'No'}
      </span>
    </div>
  );
}
