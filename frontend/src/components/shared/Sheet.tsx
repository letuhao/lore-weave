import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { cn } from '@/lib/utils';

// Sheet — the mobile bottom-sheet primitive (spec D-MOB-2, MB4). Built on Radix
// Dialog so we inherit focus-trap, Escape-to-close, portal + scroll-lock, and the
// aria wiring for free; styled as a bottom-anchored sheet instead of a centred modal.
//
// The load-bearing property (MB4) is ADDRESSABILITY: which sheet is open lives in the
// URL `?sheet=<id>` search param, not local component state. So a push/feed deep-link
// (`/entry/123?sheet=today`) restores tab + sheet, and the hardware Back button closes
// the sheet (it pops the pushed history entry) instead of navigating away from the page.
//
// History discipline: openSheet() PUSHES (adds a history entry → Back closes the sheet);
// closeSheet() REPLACES (strips the param in place → no dangling entry that Back would
// re-open). Radix's own close paths (X button, Escape, backdrop) route through
// onOpenChange(false) → closeSheet(), so every close is consistent.

const SHEET_PARAM = 'sheet';

export interface SheetRoute {
  /** The id of the currently-open sheet, or null. */
  activeSheet: string | null;
  /** Open a sheet by id — pushes a history entry so hardware Back closes it. */
  openSheet: (id: string) => void;
  /** Close the open sheet — replaces in place so no re-openable entry lingers. */
  closeSheet: () => void;
}

export function useSheetRoute(): SheetRoute {
  const [params, setParams] = useSearchParams();
  const activeSheet = params.get(SHEET_PARAM);

  const openSheet = useCallback(
    (id: string) => {
      setParams(
        (prev) => {
          // Already open on this id → no-op (return prev unchanged). Without this, a
          // double-tap / re-render pushes a SECOND identical ?sheet entry, so the first
          // hardware Back pops to the other open-sheet entry and the sheet stays open —
          // defeating the close-on-Back guarantee (cold-review L3).
          if (prev.get(SHEET_PARAM) === id) return prev;
          const next = new URLSearchParams(prev);
          next.set(SHEET_PARAM, id);
          return next;
        },
        // push (default): a new history entry so the OS/browser Back closes the sheet.
        { replace: false },
      );
    },
    [setParams],
  );

  const closeSheet = useCallback(() => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete(SHEET_PARAM);
        return next;
      },
      // replace: strip the param in place — no leftover entry that Back would re-open.
      { replace: true },
    );
  }, [setParams]);

  return { activeSheet, openSheet, closeSheet };
}

export interface SheetProps {
  /** The addressable id — the sheet is open iff `?sheet=<id>`. */
  id: string;
  title: string;
  /** Optional visually-hidden description for screen readers. */
  description?: string;
  children: React.ReactNode;
  /** Extra classes for the content panel. */
  className?: string;
  /** Anchor style: 'bottom' = phone bottom-sheet (default); 'center' = a centered dialog for wide
   *  viewports (D-A2 — the assistant reuses these sheets on desktop, where a bottom-sheet reads oddly). */
  variant?: 'bottom' | 'center';
}

export function Sheet({ id, title, description, children, className, variant = 'bottom' }: SheetProps) {
  const { t } = useTranslation();
  const { activeSheet, closeSheet } = useSheetRoute();
  const open = activeSheet === id;
  const centered = variant === 'center';

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        // Any Radix-initiated close (X / Escape / backdrop) strips the param.
        if (!next) closeSheet();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
          data-testid={`sheet-overlay-${id}`}
        />
        <Dialog.Content
          data-testid={`sheet-${id}`}
          data-variant={variant}
          className={cn(
            'fixed z-50 overflow-y-auto bg-background shadow-xl',
            centered
              ? // Desktop: a centered dialog, capped width, rounded on all sides.
                'left-1/2 top-1/2 max-h-[85dvh] w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border p-1 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0'
              : // Mobile: bottom-anchored sheet.
                'inset-x-0 bottom-0 max-h-[90dvh] rounded-t-2xl border-t pb-[max(env(safe-area-inset-bottom),1rem)] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom',
            className,
          )}
        >
          {/* Grab handle (decorative) — only meaningful on the phone bottom-sheet. */}
          {!centered && <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-muted" aria-hidden="true" />}
          <div className="flex items-start justify-between px-4 pb-2 pt-3">
            <Dialog.Title className="font-serif text-base font-semibold">{title}</Dialog.Title>
            <Dialog.Close
              aria-label={t('common.close')}
              className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </Dialog.Close>
          </div>
          {description ? (
            <Dialog.Description className="px-4 pb-2 text-sm text-muted-foreground">
              {description}
            </Dialog.Description>
          ) : (
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}
          <div className="px-4 pb-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
