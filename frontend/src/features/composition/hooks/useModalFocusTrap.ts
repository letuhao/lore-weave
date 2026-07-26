// WS-E a11y (D-T5.5-FOCUS-TRAP + D-T5.5-ESC-PROPAGATION) — a focus-trap for a
// modal overlay (role=dialog aria-modal). On open it moves focus INTO the dialog
// (so Tab can't reach the visually-hidden editor behind it), cycles Tab/Shift+Tab
// within the dialog's focusables, handles Escape, and RESTORES focus to the
// trigger element on close. The Escape handler `stopPropagation()`s so a sibling
// window-level Esc consumer (e.g. an editor shortcut) can't ALSO fire on the same
// keypress (ESC-PROPAGATION) — the listener is on the dialog element, so the event
// is halted before it bubbles to document/window.
import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function useModalFocusTrap(
  ref: RefObject<HTMLElement | null>,
  onEscape: () => void,
): void {
  // Keep the callback in a ref so the effect runs ONCE on mount — a fresh onEscape
  // closure each parent render must NOT re-run the effect (that would re-steal focus
  // + re-capture a wrong "previously focused" element every render).
  const escRef = useRef(onEscape);
  escRef.current = onEscape;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const previouslyFocused = (typeof document !== 'undefined'
      ? document.activeElement
      : null) as HTMLElement | null;

    const focusables = () => Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE));
    // Focus the first focusable (the switcher) on open; fall back to the dialog.
    (focusables()[0] ?? el).focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        escRef.current();
        return;
      }
      if (e.key !== 'Tab') return;
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      // Wrap at the ends so Tab never escapes the dialog to the editor behind it.
      if (e.shiftKey && (active === first || active === el)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    el.addEventListener('keydown', onKeyDown);
    return () => {
      el.removeEventListener('keydown', onKeyDown);
      // Restore focus to whatever opened the dialog (the trigger).
      previouslyFocused?.focus?.();
    };
    // ref identity is stable (useRef); run once for the dialog's lifetime.
  }, [ref]);
}
