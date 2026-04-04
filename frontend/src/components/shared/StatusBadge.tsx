import { cn } from '@/lib/utils';
import { Lock, Link2, Globe, Loader2, Check, X } from 'lucide-react';

type Variant =
  | 'private' | 'unlisted' | 'public'
  | 'active' | 'trashed' | 'purge_pending'
  | 'running' | 'pending' | 'completed' | 'failed'
  | 'translated' | 'not_started' | 'partial';

const config: Record<Variant, { label: string; className: string; icon?: React.ElementType }> = {
  // Visibility
  private:       { label: 'Private',       className: 'bg-secondary text-muted-foreground',              icon: Lock },
  unlisted:      { label: 'Unlisted',      className: 'bg-info/10 text-info',                            icon: Link2 },
  public:        { label: 'Public',        className: 'bg-success/10 text-success',                      icon: Globe },
  // Lifecycle
  active:        { label: 'Active',        className: 'bg-success/10 text-success' },
  trashed:       { label: 'Trashed',       className: 'bg-warning/10 text-warning' },
  purge_pending: { label: 'Purge pending', className: 'bg-destructive/10 text-destructive' },
  // Job / Translation status
  running:       { label: 'Running',       className: 'bg-info/10 text-info',                            icon: Loader2 },
  pending:       { label: 'Pending',       className: 'bg-secondary text-muted-foreground' },
  completed:     { label: 'Completed',     className: 'bg-success/10 text-success',                      icon: Check },
  failed:        { label: 'Failed',        className: 'bg-destructive/10 text-destructive',              icon: X },
  translated:    { label: 'Translated',    className: 'bg-success/10 text-success',                      icon: Check },
  not_started:   { label: 'Not started',   className: 'bg-secondary text-muted-foreground' },
  partial:       { label: 'Partial',       className: 'bg-warning/10 text-warning' },
};

interface StatusBadgeProps {
  variant: Variant;
  label?: string;
  className?: string;
}

export function StatusBadge({ variant, label, className }: StatusBadgeProps) {
  const c = config[variant];
  const Icon = c.icon;

  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium',
      c.className,
      className,
    )}>
      {Icon && (
        <Icon className={cn('h-3 w-3', variant === 'running' && 'animate-spin')} />
      )}
      {!Icon && (variant === 'active' || variant === 'trashed' || variant === 'purge_pending' || variant === 'pending' || variant === 'not_started') && (
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
      )}
      {label ?? c.label}
    </span>
  );
}
