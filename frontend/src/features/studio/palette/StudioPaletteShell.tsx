// The shared palette modal (#06a Quick Open + #06b Command Palette learn one overlay). A dimmed
// backdrop over a centred input + result list; ↑↓ move, Enter selects, Esc closes. The owner
// supplies already-filtered `entries`; the shell owns only presentation + keyboard selection.
//
// Not virtualized: both callers cap their lists (Quick Open ≤30 server hits, Command Palette a
// bounded command set), so the >50-row virtualization the spec allows for isn't needed yet.
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { PaletteEntry } from './types';

interface Props {
  open: boolean;
  onClose: () => void;
  query: string;
  onQueryChange: (q: string) => void;
  placeholder: string;
  entries: PaletteEntry[];
  onSelect: (entry: PaletteEntry) => void;
  emptyText: string;
  searching?: boolean;
  testid?: string;
}

export function StudioPaletteShell({
  open, onClose, query, onQueryChange, placeholder, entries, onSelect, emptyText, searching, testid,
}: Props) {
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Autofocus + reset the highlight to the top whenever the palette opens (a stale highlight
  // from the previous session must not carry over, even if the query is unchanged/empty).
  useEffect(() => { if (open) { inputRef.current?.focus(); setActive(0); } }, [open]);
  // A new query re-ranks the list → reset the highlight to the top.
  useEffect(() => { setActive(0); }, [query]);
  // Keep the active row in view during keyboard nav.
  useLayoutEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    el?.scrollIntoView?.({ block: 'nearest' }); // jsdom has no scrollIntoView — optional-call it
  }, [active, open, entries]);

  if (!open) return null;

  const clampedActive = Math.min(active, Math.max(0, entries.length - 1));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => (entries.length ? (Math.min(a, entries.length - 1) + 1) % entries.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (entries.length ? (Math.min(a, entries.length - 1) + entries.length - 1) % entries.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const entry = entries[clampedActive];
      if (entry) onSelect(entry);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'Tab') {
      e.preventDefault(); // trap focus in the palette
    }
  };

  let lastGroup: string | undefined;

  return (
    <div
      data-testid={testid ?? 'studio-palette'}
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh]"
      onMouseDown={onClose} // backdrop click closes
    >
      <div className="absolute inset-0 bg-black/60" aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        className="relative flex max-h-[62vh] w-[560px] max-w-[92vw] flex-col overflow-hidden rounded-lg border bg-card shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()} // clicks inside don't close
      >
        <input
          ref={inputRef}
          data-testid="palette-input"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className="h-11 flex-shrink-0 border-b bg-transparent px-4 text-sm text-foreground outline-none placeholder:text-muted-foreground/60"
        />
        <div ref={listRef} data-testid="palette-list" className="min-h-0 flex-1 overflow-y-auto py-1">
          {entries.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs text-muted-foreground" data-testid="palette-empty">
              {searching ? '…' : emptyText}
            </div>
          ) : (
            entries.map((entry, i) => {
              const header = entry.group && entry.group !== lastGroup ? entry.group : null;
              lastGroup = entry.group;
              const isActive = i === clampedActive;
              return (
                <div key={entry.id}>
                  {header && (
                    <div className="px-4 pb-0.5 pt-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                      {header}
                    </div>
                  )}
                  <button
                    type="button"
                    data-testid={`palette-entry-${entry.id}`}
                    data-active={isActive}
                    onMouseMove={() => setActive(i)}
                    onClick={() => onSelect(entry)}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-4 py-1.5 text-left text-sm',
                      isActive ? 'bg-primary/10 text-primary' : 'text-foreground hover:bg-secondary',
                    )}
                  >
                    {entry.icon && <span className="flex h-4 w-4 flex-shrink-0 items-center justify-center">{entry.icon}</span>}
                    <span className="min-w-0 flex-1 truncate">{entry.label}</span>
                    {entry.sublabel && (
                      <span className="flex-shrink-0 truncate text-[11px] text-muted-foreground">{entry.sublabel}</span>
                    )}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
