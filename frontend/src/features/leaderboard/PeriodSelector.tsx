import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

const periods = [
  { key: '7d', labelKey: 'period.7d' },
  { key: '30d', labelKey: 'period.30d' },
  { key: 'all', labelKey: 'period.all' },
] as const;

export function PeriodSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation('leaderboard');

  return (
    <div className="flex gap-0.5 rounded-md bg-secondary p-0.5">
      {periods.map((p) => (
        <button
          key={p.key}
          onClick={() => onChange(p.key)}
          className={cn(
            'rounded px-2.5 py-1 text-[11px] font-medium transition-colors',
            value === p.key
              ? 'bg-primary/15 text-primary'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t(p.labelKey)}
        </button>
      ))}
    </div>
  );
}
