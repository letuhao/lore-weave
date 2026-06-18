import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { type ReactNode } from 'react';

interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function FormDialog({ open, onOpenChange, title, description, children, footer }: FormDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        {/* C0 (BL-4/KN-3): the dialog is a flex column capped at 85vh.
            The header and footer are flex-shrink-0 (always visible); only
            the body scrolls. This keeps the primary action reachable on
            tall forms instead of pushing it below the viewport fold. The
            body and footer are SIBLINGS (not nested) so the pinned footer
            never overlaps scrolled content. */}
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-background shadow-lg">
          <div className="flex-shrink-0 px-6 pt-6">
            <Dialog.Title className="font-serif text-lg font-semibold">{title}</Dialog.Title>
            {/* Gate-5-I2: always render Description so Radix doesn't
                warn about missing aria-describedby. When the caller
                doesn't supply visible copy, fall back to an sr-only
                announcement that mirrors the title — gives screen
                readers something to read without changing the visual
                layout for sighted users. */}
            <Dialog.Description
              className={
                description
                  ? 'mt-1 text-sm text-muted-foreground'
                  : 'sr-only'
              }
            >
              {description ?? title}
            </Dialog.Description>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">{children}</div>

          {footer && (
            <div className="flex-shrink-0 flex justify-end gap-2 border-t px-6 py-4">{footer}</div>
          )}

          <Dialog.Close asChild>
            <button
              className="absolute right-4 top-4 rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
