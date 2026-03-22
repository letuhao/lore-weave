import { Button } from '@/components/ui/button';

type Props = {
  selectedCount: number;
  onTranslate: () => void;
  onClear: () => void;
};

export function FloatingActionBar({ selectedCount, onTranslate, onClear }: Props) {
  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2">
      <div className="flex items-center gap-3 rounded-full border bg-background px-5 py-3 shadow-lg">
        <span className="text-sm font-medium">
          {selectedCount} chapter{selectedCount !== 1 ? 's' : ''} selected
        </span>
        <Button size="sm" onClick={onTranslate}>
          Translate
        </Button>
        <button
          onClick={onClear}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
