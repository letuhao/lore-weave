import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

// Shared presentation primitives for every K19a.3 state card.
// Cards stay "dumb": layout + text via i18n + callback buttons. All real
// data fetching and state derivation live one level up (K19a.4 hook).

interface ShellProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

export function StateCardShell({ label, children, className }: ShellProps) {
  return (
    <div className={cn('rounded-lg border bg-card px-4 py-3.5', className)}>
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="space-y-2.5 text-[13px]">{children}</div>
    </div>
  );
}

type ButtonVariant = 'primary' | 'secondary' | 'destructive';

interface ActionButtonProps {
  onClick: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  children: React.ReactNode;
}

export function StateActionButton({
  onClick,
  variant = 'secondary',
  disabled,
  children,
}: ActionButtonProps) {
  const variantClass = {
    primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
    secondary: 'border text-muted-foreground hover:bg-secondary hover:text-foreground',
    destructive: 'border border-destructive/30 text-destructive hover:bg-destructive/10',
  }[variant];

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
        variantClass,
      )}
    >
      {children}
    </button>
  );
}

interface ProgressBarProps {
  processed: number;
  total: number | null;
}

export function ProgressBar({ processed, total }: ProgressBarProps) {
  const pct =
    total && total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full bg-primary transition-all"
        style={{ width: `${pct}%` }}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        role="progressbar"
      />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('h-3.5 w-3.5 animate-spin', className)} />;
}
