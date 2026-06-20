import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Undo2 } from 'lucide-react';
import type { ActivityEvent } from '../types';

// MCP fan-out (C-ACTIVITY) — the Tier-A activity / Undo strip.
//
// Every auto-applied (Tier-A) op the agent ran this turn streams an `activity`
// event ({op, summary, undo}); this renders them as a compact strip under the
// assistant message. When `undo.available`, an Undo button issues the named
// reverse tool (trash/restore, restoreRevision, set-back) via the `onUndo`
// callback the parent wires to a fresh agent turn — the component itself stays a
// pure renderer (no API calls).

interface Props {
  activities: ActivityEvent[];
  /** Issue the named reverse tool for an activity (parent drives a new turn). */
  onUndo: (activity: ActivityEvent) => unknown;
  /** Disable the Undo buttons while a turn is in flight. */
  disabled?: boolean;
}

export function ActivityStrip({ activities, onUndo, disabled }: Props) {
  const { t } = useTranslation('chat');
  // Track which activities the user already undid (by index) so the button
  // doesn't re-fire and the row shows an "Undone" affordance.
  const [undone, setUndone] = useState<Set<number>>(new Set());

  if (activities.length === 0) return null;

  function handleUndo(activity: ActivityEvent, idx: number) {
    if (undone.has(idx)) return;
    setUndone((prev) => new Set(prev).add(idx));
    void onUndo(activity);
  }

  return (
    <div
      data-testid="activity-strip"
      className="mt-1.5 space-y-1 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-2 text-xs"
    >
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-500">
        <Sparkles className="h-3 w-3" />
        {t('activity.label', { defaultValue: 'Done for you' })}
      </div>
      <ul className="space-y-1">
        {activities.map((a, i) => {
          const canUndo = a.undo?.available === true && !!a.undo.tool;
          const isUndone = undone.has(i);
          return (
            <li
              key={i}
              data-testid="activity-row"
              className="flex items-center justify-between gap-2 rounded bg-background/60 px-1.5 py-1 text-[11px]"
            >
              <span className="min-w-0 truncate text-foreground/90">{a.summary}</span>
              {canUndo && (
                <button
                  type="button"
                  data-testid="activity-undo"
                  onClick={() => handleUndo(a, i)}
                  disabled={disabled || isUndone}
                  className="inline-flex shrink-0 items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  <Undo2 className="h-3 w-3" />
                  {isUndone
                    ? t('activity.undone', { defaultValue: 'Undone' })
                    : t('activity.undo', { defaultValue: 'Undo' })}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
