import type { ReactNode } from 'react';
import { TierChip } from '@/features/glossary/components/tiering/TierChip';
import type { Tier } from '@/features/glossary/tieringTypes';

/**
 * One standards row — icon, name, code, tier chip, and an actions slot. Render-only;
 * the panel owns the data + handlers (MVC view).
 */
export function StandardRow({
  icon,
  name,
  code,
  tier,
  children,
}: {
  icon: string;
  name: string;
  code: string;
  tier: Tier;
  children?: ReactNode;
}) {
  return (
    <div
      className="flex items-center gap-3 rounded-md border px-3 py-2"
      data-testid={`standard-row-${code}`}
    >
      <span className="text-lg leading-none" aria-hidden>
        {icon || '•'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-medium">{name}</span>
          <TierChip tier={tier} />
        </div>
        <code className="text-[11px] text-muted-foreground">{code}</code>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">{children}</div>
    </div>
  );
}
