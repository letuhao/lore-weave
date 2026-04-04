import { useState, useRef, useEffect } from 'react';
import { BookOpen, FileText, Paperclip, Plus, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ContextPicker } from './ContextPicker';
import type { ContextItem } from './types';

interface ContextBarProps {
  items: ContextItem[];
  onAttach: (item: ContextItem) => void;
  onDetach: (id: string) => void;
  onClearAll: () => void;
}

const PILL_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  book:     { bg: 'bg-primary/10',   border: 'border-primary/20',  text: 'text-primary' },
  chapter:  { bg: 'bg-accent/10',    border: 'border-accent/20',   text: 'text-accent' },
  glossary: { bg: 'bg-blue-500/8',   border: 'border-blue-500/15', text: 'text-blue-400' },
};

const PILL_ICON: Record<string, React.ReactNode> = {
  book: <BookOpen className="h-[11px] w-[11px]" />,
  chapter: <FileText className="h-[11px] w-[11px]" />,
  glossary: null,
};

export function ContextBar({ items, onAttach, onDetach, onClearAll }: ContextBarProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const hasItems = items.length > 0;

  return (
    <>
      {/* Attach button (when no items, shown as icon inside input) */}
      {!hasItems && (
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="absolute bottom-2 left-2 z-10 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          title="Attach context"
        >
          <Paperclip className="h-4 w-4" />
        </button>
      )}

      {/* Context pills bar (when items attached) */}
      {hasItems && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-3.5 py-2">
          <button
            type="button"
            onClick={() => setPickerOpen(!pickerOpen)}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Plus className="h-3 w-3" />
            Context
          </button>

          {items.map((item) => {
            const style = PILL_STYLES[item.type] ?? PILL_STYLES.book;
            return (
              <span
                key={item.id}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium',
                  style.bg, style.border, style.text,
                )}
              >
                {item.type === 'glossary' && item.kindColor ? (
                  <span className="h-2 w-2 rounded-full" style={{ background: item.kindColor }} />
                ) : (
                  PILL_ICON[item.type]
                )}
                <span className="max-w-[140px] truncate">{item.label}</span>
                <button
                  type="button"
                  onClick={() => onDetach(item.id)}
                  className="ml-0.5 opacity-50 transition-opacity hover:opacity-100"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            );
          })}

          {items.length > 1 && (
            <button type="button" onClick={onClearAll} className="text-[10px] text-muted-foreground hover:text-foreground">
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Floating picker modal — renders via portal-like fixed overlay */}
      {pickerOpen && (
        <div
          className="fixed inset-0 z-50"
          onClick={() => setPickerOpen(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setPickerOpen(false); }}
          role="dialog"
          aria-modal="true"
          aria-label="Context picker"
        >
          {/* Semi-transparent backdrop */}
          <div className="absolute inset-0 bg-black/30" />

          {/* Centered floating panel */}
          <div
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            onClick={(e) => e.stopPropagation()}
          >
            <ContextPicker
              attached={items}
              onAttach={(item) => onAttach(item)}
              onDetach={onDetach}
              onClose={() => setPickerOpen(false)}
            />
          </div>
        </div>
      )}
    </>
  );
}
