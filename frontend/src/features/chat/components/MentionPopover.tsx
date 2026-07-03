import { useTranslation } from 'react-i18next';
import { BookOpen, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MentionCandidate } from '../hooks/useMentionPicker';

interface MentionPopoverProps {
  open: boolean;
  items: MentionCandidate[];
  selectedIndex: number;
  onSelect: (item: MentionCandidate) => void;
  onHighlight: (index: number) => void;
}

const optionId = (i: number) => `chat-mention-option-${i}`;

/**
 * Inline @-mention listbox, anchored above the chat input. Render-only — all
 * state lives in useMentionPicker, so unmounting when closed is safe.
 */
export function MentionPopover({ open, items, selectedIndex, onSelect, onHighlight }: MentionPopoverProps) {
  const { t } = useTranslation('chat');
  if (!open || items.length === 0) return null;

  return (
    <div
      role="listbox"
      id="chat-mention-listbox"
      aria-label={t('context.mention.aria')}
      aria-activedescendant={optionId(selectedIndex)}
      className="absolute bottom-full left-0 z-30 mb-1 max-h-[240px] w-full overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
    >
      <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t('context.mention.title')}
      </div>
      {items.map((item, i) => (
        <button
          key={`${item.type}-${item.id}`}
          id={optionId(i)}
          type="button"
          role="option"
          aria-selected={i === selectedIndex}
          // preventDefault keeps focus in the textarea (no focus steal on click)
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSelect(item)}
          onMouseEnter={() => onHighlight(i)}
          className={cn(
            'flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors',
            i === selectedIndex ? 'bg-accent/10 text-foreground' : 'text-muted-foreground hover:bg-secondary',
          )}
        >
          <span className="flex h-5 w-5 shrink-0 items-center justify-center">
            {item.type === 'book' && <BookOpen className="h-3.5 w-3.5 text-primary" />}
            {item.type === 'chapter' && <FileText className="h-3.5 w-3.5 text-accent" />}
            {item.type === 'glossary' && (
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: item.kindColor ?? 'var(--muted-foreground)' }} />
            )}
          </span>
          <span className="min-w-0 flex-1 truncate text-xs font-medium">{item.label}</span>
          {item.detail && (
            <span className="max-w-[120px] shrink-0 truncate text-[10px] text-muted-foreground">{item.detail}</span>
          )}
        </button>
      ))}
    </div>
  );
}
