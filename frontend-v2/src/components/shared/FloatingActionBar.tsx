import { type ReactNode } from 'react';

interface FloatingActionBarProps {
  children: ReactNode;
  visible: boolean;
}

export function FloatingActionBar({ children, visible }: FloatingActionBarProps) {
  if (!visible) return null;

  return (
    <div className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2" style={{ animation: 'float-bar-in 200ms ease-out' }}>
      <div
        className="flex items-center gap-3 rounded-full border bg-background px-5 py-2.5"
        style={{ boxShadow: '0 4px 32px rgba(0,0,0,0.6), 0 0 0 1px hsl(var(--border))' }}
      >
        {children}
      </div>
    </div>
  );
}

export function FloatingActionDivider() {
  return <div className="h-4 w-px bg-border" />;
}
