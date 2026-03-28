import * as React from 'react';
import { cn } from '@/lib/utils';

interface ToggleProps {
  pressed: boolean;
  onPressedChange: (pressed: boolean) => void;
  className?: string;
  disabled?: boolean;
  children?: React.ReactNode;
  'aria-label'?: string;
}

function Toggle({ pressed, onPressedChange, className, disabled, children, ...props }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={pressed}
      disabled={disabled}
      onClick={() => onPressedChange(!pressed)}
      className={cn(
        'inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors hover:bg-muted hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        pressed && 'bg-accent text-accent-foreground',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export { Toggle };
