import { Plus } from 'lucide-react';

interface ChunkInsertRowProps {
  onInsert: () => void;
}

export function ChunkInsertRow({ onInsert }: ChunkInsertRowProps) {
  return (
    <div className="group flex h-4 items-center px-8">
      <button
        onClick={(e) => { e.stopPropagation(); onInsert(); }}
        className="flex w-full items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100"
        title="Insert paragraph here"
      >
        <div className="h-px flex-1 bg-border/60" />
        <span className="flex items-center gap-1 rounded-full border border-border/60 bg-background px-2 py-px text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary">
          <Plus className="h-2.5 w-2.5" />
          insert
        </span>
        <div className="h-px flex-1 bg-border/60" />
      </button>
    </div>
  );
}
