import { useState } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import TextareaAutosize from 'react-textarea-autosize';
import { ContextBar } from '../context/ContextBar';
import type { ContextItem } from '../context/types';

interface ChatInputBarProps {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  modelHint?: string;
  /** Context items attached to the next message */
  contextItems: ContextItem[];
  onAttachContext: (item: ContextItem) => void;
  onDetachContext: (id: string) => void;
  onClearContext: () => void;
}

export function ChatInputBar({
  onSend,
  onStop,
  isStreaming,
  disabled,
  modelHint,
  contextItems,
  onAttachContext,
  onDetachContext,
  onClearContext,
}: ChatInputBarProps) {
  const [value, setValue] = useState('');

  function handleSubmit() {
    const text = value.trim();
    if (!text || isStreaming) return;
    setValue('');
    onSend(text);
  }

  const hasContext = contextItems.length > 0;

  return (
    <div className="shrink-0 border-t border-border bg-card px-8 py-4">
      <div className="mx-auto max-w-[720px]">
        <div className="relative overflow-visible rounded-[10px] border border-border bg-background focus-within:border-ring focus-within:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]">
          {/* Context bar (pills + attach button) */}
          <ContextBar
            items={contextItems}
            onAttach={onAttachContext}
            onDetach={onDetachContext}
            onClearAll={onClearContext}
          />

          {/* Textarea */}
          <TextareaAutosize
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Ask about your story, characters, world-building..."
            minRows={3}
            maxRows={8}
            disabled={disabled || isStreaming}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            className={`w-full resize-none border-none bg-transparent py-3 pr-12 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/50 focus:outline-none disabled:opacity-50 ${hasContext ? 'px-3.5' : 'pl-10 pr-12'}`}
          />

          {/* Send / Stop button */}
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              title="Stop generating"
              className="absolute right-2 bottom-2 flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-destructive text-destructive-foreground transition-colors hover:bg-destructive/90"
            >
              <Square className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!value.trim() || disabled}
              title="Send (Enter)"
              className="absolute right-2 bottom-2 flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          )}
        </div>
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          {hasContext ? 'Context attached \u00B7 ' : ''}
          {modelHint ? `${modelHint} \u00B7 ` : ''}Enter to send \u00B7 Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
