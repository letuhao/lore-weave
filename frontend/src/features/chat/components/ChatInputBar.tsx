import type { ChangeEvent } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import TextareaAutosize from 'react-textarea-autosize';
import { Button } from '@/components/ui/button';

interface ChatInputBarProps {
  value: string;
  onChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  onSubmit: () => void;
  isLoading: boolean;
  onStop: () => void;
  disabled?: boolean;
}

export function ChatInputBar({
  value,
  onChange,
  onSubmit,
  isLoading,
  onStop,
  disabled,
}: ChatInputBarProps) {
  return (
    <div className="shrink-0 border-t bg-background px-4 py-3">
      <div className="flex items-end gap-2 rounded-xl border bg-muted/30 px-3 py-2 focus-within:ring-1 focus-within:ring-ring">
        <TextareaAutosize
          value={value}
          onChange={onChange}
          placeholder="Message…"
          minRows={1}
          maxRows={8}
          disabled={disabled || isLoading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (value.trim() && !isLoading) onSubmit();
            }
          }}
          className="flex-1 resize-none bg-transparent text-sm leading-relaxed focus:outline-none disabled:opacity-50"
        />
        {isLoading ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 w-7 shrink-0 rounded-full p-0 text-destructive hover:bg-destructive/10"
            onClick={onStop}
            title="Stop generating"
          >
            <Square className="h-3.5 w-3.5" />
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            className="h-7 w-7 shrink-0 rounded-full p-0"
            disabled={!value.trim() || disabled}
            onClick={onSubmit}
            title="Send (Enter)"
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      <p className="mt-1.5 text-center text-[10px] text-muted-foreground/50">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
