// C8 / SD-C8 (WS-5.3/5.6) — the weekly-reflection card. Renders the descriptive reflection DRAFT
// (a diary entry with journal_kind='reflection') + the surfaced patterns, each with a DISMISS button.
// Dismissing tombstones the pattern permanently (C2): worker-ai drops that period-independent
// pattern_key AT DETECTION, so it never resurfaces. Pure view — dismiss is a callback from the hook.
import { useState } from 'react';
import type { DiaryEntry, ReflectionPattern } from '../types';

interface Props {
  reflection: DiaryEntry;
  patterns: ReflectionPattern[];
  onDismiss: (patternKey: string) => Promise<void>;
}

export function ReflectionCard({ reflection, patterns, onDismiss }: Props) {
  const [dismissing, setDismissing] = useState<Record<string, boolean>>({});
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});

  const handleDismiss = async (key: string) => {
    setDismissing((s) => ({ ...s, [key]: true }));
    setFailed((s) => ({ ...s, [key]: false }));
    try {
      await onDismiss(key);
      setDismissed((s) => ({ ...s, [key]: true })); // optimistic hide (server is SoT; no localStorage)
    } catch {
      // cold-review LOW-4 — a failed dismiss must NOT hide the pattern; surface a retry-able error
      // (the pattern stays visible, the user is told it didn't stick).
      setFailed((s) => ({ ...s, [key]: true }));
    } finally {
      setDismissing((s) => ({ ...s, [key]: false }));
    }
  };

  const visible = patterns.filter((p) => !dismissed[p.pattern_key]);

  return (
    <div data-testid="reflection-card" className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-2 text-sm font-semibold">{reflection.title || 'Weekly reflection'}</h3>

      {/* The descriptive draft (Socratic prompts + observations). Rendered as pre-wrapped text. */}
      <p data-testid="reflection-body" className="whitespace-pre-wrap text-sm text-muted-foreground">
        {reflection.body}
      </p>

      {visible.length > 0 && (
        <ul data-testid="reflection-patterns" className="mt-3 space-y-2">
          {visible.map((p) => (
            <li key={p.pattern_key} data-testid="reflection-pattern" className="flex items-start justify-between gap-3">
              <span className="text-sm">
                {p.summary}
                {failed[p.pattern_key] && (
                  <span data-testid="dismiss-error" className="ml-2 text-xs text-destructive">
                    couldn’t dismiss — try again
                  </span>
                )}
              </span>
              <button
                type="button"
                data-testid="dismiss-pattern"
                disabled={!!dismissing[p.pattern_key]}
                onClick={() => void handleDismiss(p.pattern_key)}
                className="shrink-0 rounded border border-border px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
              >
                {dismissing[p.pattern_key] ? 'Dismissing…' : 'Dismiss'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
