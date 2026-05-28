import { useState } from 'react';
import { Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolCallRecord } from '../types';

// K21-C (D2): the tool-call indicator on assistant messages.
//
// Renders a compact chip row from `message.tool_calls` — one chip per
// memory tool the assistant invoked during its turn. Clicking the row
// expands a detail list (tool name, ok/failed, iteration if known).
//
// Mirrors MemoryIndicator's style: bordered pill, click-to-expand, no
// useEffect — the open/close is a plain useState toggle. Works from
// both the live accumulated list (useChatMessages) and the persisted
// `tool_calls` column (replay). Renders nothing when there are no
// tool calls, so MessageBubble can mount it unconditionally.

interface Props {
  toolCalls: ToolCallRecord[];
}

// Tool name → human-readable label. Verbatim from the K21-C spec.
// An unrecognised tool name falls back to the raw name with a gear,
// so a new BE tool doesn't render blank.
const TOOL_LABELS: Record<string, string> = {
  memory_search: '🔍 Searched memory',
  memory_recall_entity: '📚 Recalled an entity',
  memory_timeline: '📅 Checked the timeline',
  memory_remember: '📝 Noted a memory',
  memory_forget: '🗑 Forgot a fact',
};

function labelFor(tool: string): string {
  return TOOL_LABELS[tool] ?? `⚙ ${tool}`;
}

export function ToolCallIndicator({ toolCalls }: Props) {
  const [expanded, setExpanded] = useState(false);

  // Empty / null → render nothing. Lets the parent mount this
  // unconditionally without a guard of its own.
  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="mt-1.5" data-testid="tool-call-indicator">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded ? 'true' : 'false'}
        title="Tools used in this reply"
        className="flex flex-wrap items-center gap-1.5 rounded-md border border-border bg-secondary/40 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary"
      >
        <Wrench className="h-3 w-3 shrink-0 text-accent" />
        {toolCalls.map((tc, i) => (
          <span
            key={i}
            data-testid="tool-call-chip"
            className={cn(
              'inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 font-medium',
              tc.ok
                ? 'border-accent/25 bg-accent/10 text-accent'
                : 'border-destructive/30 bg-destructive/10 text-destructive',
            )}
          >
            {labelFor(tc.tool)}
          </span>
        ))}
      </button>

      {expanded && (
        <ul
          data-testid="tool-call-detail"
          className="mt-1 space-y-0.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-[10px] text-muted-foreground"
        >
          {toolCalls.map((tc, i) => (
            <li key={i} className="flex items-center gap-1.5">
              <span
                className={cn(
                  'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
                  tc.ok ? 'bg-emerald-400' : 'bg-red-400',
                )}
              />
              <span className="text-foreground/80">{labelFor(tc.tool)}</span>
              {tc.iteration != null && (
                <span className="text-muted-foreground/60">· step {tc.iteration}</span>
              )}
              <span className={cn('ml-auto', tc.ok ? 'text-emerald-400' : 'text-red-400')}>
                {tc.ok ? 'ok' : 'failed'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
