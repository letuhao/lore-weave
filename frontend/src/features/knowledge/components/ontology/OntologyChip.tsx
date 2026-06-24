import { cn } from '@/lib/utils';
import type { PropsWithChildren } from 'react';

// Render-only chip primitive shared across the ontology views. Variants map to
// the mockup colour roles (tier-system/user/project, edge, drive, glossary,
// temporal, deprecated). No logic.
export type ChipVariant =
  | 'system'
  | 'user'
  | 'project'
  | 'edge'
  | 'drive'
  | 'glossary'
  | 'temporal'
  | 'deprecated'
  | 'neutral';

const VARIANT_CLASS: Record<ChipVariant, string> = {
  system: 'bg-indigo-100 text-indigo-700',
  user: 'bg-violet-100 text-violet-700',
  project: 'bg-sky-100 text-sky-700',
  edge: 'bg-blue-100 text-blue-700',
  drive: 'bg-emerald-100 text-emerald-700',
  glossary: 'bg-teal-100 text-teal-700',
  temporal: 'bg-amber-100 text-amber-700',
  deprecated: 'bg-rose-100 text-rose-700',
  neutral: 'bg-slate-100 text-slate-600',
};

export function OntologyChip({
  variant = 'neutral',
  className,
  children,
}: PropsWithChildren<{ variant?: ChipVariant; className?: string }>) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium',
        VARIANT_CLASS[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
