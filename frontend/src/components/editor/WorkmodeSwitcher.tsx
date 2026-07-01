// The chapter workspace's primary MODE switcher (view).
//
// One obvious dropdown button — Write / Translate / Read / Compose — replacing the old
// scatter of Pen/Sparkles toggles, the Co-write bridge, and the one-off Translate button.
// Render-only: the page owns the state (useWorkmode) and the reader navigation; this
// component just presents the current mode and reports selections. "Read" is an action
// (opens the full ReaderPage route), not a persisted mode, so it calls onOpenReader.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pen, Languages, BookOpen, Sparkles, ChevronDown, type LucideIcon } from 'lucide-react';
import type { Workmode } from '@/hooks/useWorkmode';
import { cn } from '@/lib/utils';

interface Props {
  mode: Workmode;
  onChange: (mode: Workmode) => void;
  /** Open the full reader (a route, not an in-editor mode). */
  onOpenReader: () => void;
}

type Item =
  | { key: Workmode; action: 'mode'; icon: LucideIcon; labelKey: string; descKey: string }
  | { key: 'read'; action: 'reader'; icon: LucideIcon; labelKey: string; descKey: string };

const ITEMS: Item[] = [
  { key: 'write', action: 'mode', icon: Pen, labelKey: 'workmode.write', descKey: 'workmode.write_desc' },
  { key: 'translate', action: 'mode', icon: Languages, labelKey: 'workmode.translate', descKey: 'workmode.translate_desc' },
  { key: 'read', action: 'reader', icon: BookOpen, labelKey: 'workmode.read', descKey: 'workmode.read_desc' },
  { key: 'compose', action: 'mode', icon: Sparkles, labelKey: 'workmode.compose', descKey: 'workmode.compose_desc' },
];

export function WorkmodeSwitcher({ mode, onChange, onOpenReader }: Props) {
  const { t } = useTranslation('editor');
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside-click / Escape (subscription synchronization — the allowed use of
  // useEffect; the selection handlers below are direct, not effect-driven).
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const current = ITEMS.find((i) => i.key === mode) ?? ITEMS[0];
  const CurrentIcon = current.icon;

  const select = (item: Item) => {
    setOpen(false);
    if (item.action === 'reader') onOpenReader();
    else onChange(item.key);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        data-testid="workmode-switcher"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-md border bg-muted/30 px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-muted/60"
      >
        <CurrentIcon className="h-3.5 w-3.5 text-primary" />
        {t(current.labelKey, { defaultValue: current.key })}
        <ChevronDown className={cn('h-3 w-3 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div
          role="menu"
          data-testid="workmode-menu"
          className="absolute left-0 top-full z-40 mt-1 w-56 overflow-hidden rounded-md border bg-popover p-1 shadow-lg"
        >
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const active = item.action === 'mode' && item.key === mode;
            return (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                data-testid={`workmode-item-${item.key}`}
                onClick={() => select(item)}
                className={cn(
                  'flex w-full items-start gap-2 rounded px-2 py-1.5 text-left transition-colors',
                  active ? 'bg-primary/10 text-primary' : 'text-foreground hover:bg-secondary',
                )}
              >
                <Icon className={cn('mt-0.5 h-3.5 w-3.5 flex-shrink-0', active ? 'text-primary' : 'text-muted-foreground')} />
                <span className="flex flex-col">
                  <span className="text-[11px] font-medium leading-tight">{t(item.labelKey, { defaultValue: item.key })}</span>
                  <span className="text-[10px] leading-tight text-muted-foreground">{t(item.descKey, { defaultValue: '' })}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
