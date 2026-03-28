import * as React from 'react';
import { cn } from '@/lib/utils';

/* ── Overlay ─────────────────────────────────────────────────────────────────── */

function DialogOverlay({
  className,
  onClick,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('fixed inset-0 z-50 bg-black/50 backdrop-blur-sm', className)}
      onClick={onClick}
      aria-hidden="true"
      {...props}
    />
  );
}

/* ── Content ─────────────────────────────────────────────────────────────────── */

interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {
  onClose?: () => void;
}

function DialogContent({ className, children, onClose, ...props }: DialogContentProps) {
  // Close on ESC
  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose?.();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <>
      <DialogOverlay onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-lg',
          className,
        )}
        {...props}
      >
        {children}
        {onClose && (
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-sm p-1 text-muted-foreground opacity-70 transition-opacity hover:opacity-100"
            aria-label="Close"
          >
            ✕
          </button>
        )}
      </div>
    </>
  );
}

/* ── Header / Title / Description ────────────────────────────────────────────── */

function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />;
}

function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} />;
}

function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 pt-4', className)} {...props} />;
}

export { DialogOverlay, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter };
