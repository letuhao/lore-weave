import { Languages, MessageCircle, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChunkItemProps {
  index: number;
  text: string;
  selected: boolean;
  onSelect: (index: number, shift: boolean) => void;
  onChange: (index: number, text: string) => void;
}

export function ChunkItem({ index, text, selected, onSelect, onChange }: ChunkItemProps) {
  return (
    <div
      className={cn(
        'group flex gap-3 rounded-md border py-2 pl-3 pr-2 transition-colors',
        selected
          ? 'border-primary/40 bg-primary/[0.04]'
          : 'border-border/40 hover:border-border hover:bg-card',
      )}
      onClick={(e) => onSelect(index, e.shiftKey)}
    >
      <span className="w-5 flex-shrink-0 pt-1 text-right font-mono text-[10px] text-muted-foreground/40 group-hover:text-muted-foreground">
        {index + 1}
      </span>
      <div
        className="flex-1 text-sm leading-[1.8] outline-none focus:ring-0"
        style={{ whiteSpace: 'pre-wrap' }}
        contentEditable
        suppressContentEditableWarning
        onBlur={(e) => onChange(index, e.currentTarget.innerText)}
        dangerouslySetInnerHTML={{ __html: text }}
      />
      <div className="flex flex-shrink-0 flex-col gap-1 pt-1 opacity-0 transition-opacity group-hover:opacity-60">
        <button className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground" title="Translate">
          <Languages className="h-3 w-3" />
        </button>
        <button className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground" title="Send to AI">
          <MessageCircle className="h-3 w-3" />
        </button>
        <button
          className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title="Copy"
          onClick={(e) => { e.stopPropagation(); void navigator.clipboard.writeText(text); }}
        >
          <Copy className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}
