import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { SearchX, FolderOpen, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  /** Whether this empty state is caused by active filters (shows different icon/text). */
  filtered?: boolean;
  className?: string;
}

export function EmptyState({ icon, title, description, action, filtered, className }: EmptyStateProps) {
  const defaultIcon = filtered ? (
    <SearchX className="h-10 w-10 text-muted-foreground/50" />
  ) : (
    <FolderOpen className="h-10 w-10 text-muted-foreground/50" />
  );

  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-12 text-center', className)}>
      {icon || defaultIcon}
      <div className="space-y-1">
        <h3 className="text-sm font-medium">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      {action && (
        <Button variant="outline" size="sm" onClick={action.onClick} className="mt-1">
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {action.label}
        </Button>
      )}
    </div>
  );
}
