// T4d — renders the admin chat transcript (view only). Each assistant message
// may carry tool chips; a pending glossary_confirm_action renders an
// AdminConfirmCard.
import { AdminConfirmCard } from './AdminConfirmCard';
import type { AdminToolOutcome, ChatMessage } from '../types';

interface Props {
  messages: ChatMessage[];
  streamingText: string;
  isStreaming: boolean;
  onResume: (runId: string, toolCallId: string, outcome: AdminToolOutcome) => void;
}

export function MessageList({ messages, streamingText, isStreaming, onResume }: Props) {
  return (
    <div className="flex-1 space-y-3 overflow-y-auto p-4">
      {messages.map((m) => (
        <div key={m.message_id} className={m.role === 'user' ? 'text-right' : 'text-left'}>
          <div
            className={`inline-block max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
              m.role === 'user'
                ? 'bg-secondary text-secondary-foreground'
                : 'bg-card text-foreground border border-border'
            }`}
          >
            {m.content}
            {m.tool_calls?.map((tc, i) =>
              tc.pending && tc.tool === 'glossary_confirm_action' ? (
                <AdminConfirmCard key={`${m.message_id}-${i}`} record={tc} onResume={onResume} />
              ) : (
                <div key={`${m.message_id}-${i}`} className="mt-1 text-[10px] text-muted-foreground">
                  {tc.ok ? '✓' : '✗'} {tc.tool}
                </div>
              ),
            )}
          </div>
        </div>
      ))}
      {isStreaming && (
        <div className="text-left">
          <div className="inline-block max-w-[80%] whitespace-pre-wrap rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
            {streamingText || <span className="text-muted-foreground">…</span>}
          </div>
        </div>
      )}
    </div>
  );
}
