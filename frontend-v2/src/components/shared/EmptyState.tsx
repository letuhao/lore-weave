import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  icon: React.ElementType;
  title: string;
  description?: string;
  action?: ReactNode;
  /** Icon circle color variant */
  variant?: 'default' | 'primary' | 'accent';
}

const CIRCLE_STYLES = {
  default: 'bg-secondary text-muted-foreground',
  primary: 'bg-[hsl(35_50%_18%)] text-[hsl(35_90%_72%)]',
  accent: 'bg-[hsl(170_30%_14%)] text-[hsl(170_50%_80%)]',
};

export function EmptyState({ icon: Icon, title, description, action, variant = 'default' }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border py-16 text-center">
      <div className={cn('mb-4 flex h-12 w-12 items-center justify-center rounded-full', CIRCLE_STYLES[variant])}>
        <Icon className="h-6 w-6" />
      </div>
      <p className="font-serif text-sm font-medium">{title}</p>
      {description && (
        <p className="mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
