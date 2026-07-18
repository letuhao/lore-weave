// A3 view — "Let the assistant work on its own". The opt-in controls that ARM the (previously dormant)
// autonomous jobs. Each toggle is fail-closed OFF and shows its EFFECTIVE state (on/off + the next run),
// never a hidden default. View-only — the read/write logic lives in useAssistantSchedule.
import { cn } from '@/lib/utils';
import type { AutonomousJobKind } from '../types';

interface JobMeta {
  kind: AutonomousJobKind;
  label: string;
  desc: string;
}

// The schedule-only set (each fully delivered by arming its schedule row alone). `proactive_nudge` is NOT
// here — it's double-gated (chat opt-in + schedule), so it gets a DEDICATED row via the `proactive` prop
// (wired to useProactiveSetting, which sets both). Order = most-valuable first.
const JOBS: JobMeta[] = [
  { kind: 'eod_distill', label: 'End my day automatically', desc: 'Journal the day each evening, even if you forget to.' },
  { kind: 'weekly_reflection', label: 'Weekly reflection', desc: 'A gentle weekly pattern + coaching note.' },
  { kind: 'weekly_rollup', label: 'Weekly summary', desc: 'A recap of your week.' },
  { kind: 'nudge', label: 'Reminders to journal', desc: "A nudge if you haven't ended your day." },
];

export interface AutonomousSettingsProps {
  loading: boolean;
  isEnabled: (k: AutonomousJobKind) => boolean;
  nextFireAt: (k: AutonomousJobKind) => string | null;
  savingKind: AutonomousJobKind | null;
  /** The user's effective zone (saved || detected) — feeds the schedule's local fire time. */
  timezone: string;
  onToggle: (k: AutonomousJobKind, enabled: boolean, timezone: string) => void;
  /** D-A3-PROACTIVE — proactive check-ins are double-gated (chat opt-in + schedule), so they get a
   *  dedicated row wired to useProactiveSetting (which sets BOTH). Absent ⇒ the row isn't rendered. */
  proactive?: { enabled: boolean; saving: boolean; onToggle: (on: boolean, timezone: string) => void };
}

export function AutonomousSettings({ loading, isEnabled, nextFireAt, savingKind, timezone, onToggle, proactive }: AutonomousSettingsProps) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3" data-testid="autonomous-settings">
      <div>
        <div className="text-sm font-medium">Let the assistant work on its own</div>
        <div className="text-xs text-muted-foreground">
          Off until you turn it on — these run in the background and use your models.
        </div>
      </div>

      {loading ? (
        <p className="py-2 text-xs text-muted-foreground">Loading…</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {JOBS.map((job) => {
            const on = isEnabled(job.kind);
            const busy = savingKind === job.kind;
            const next = on ? nextFireAt(job.kind) : null;
            return (
              <li key={job.kind} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="text-sm">{job.label}</div>
                  <div className="text-xs text-muted-foreground">
                    {/* Effective state, stated plainly (SET rule: never a hidden default). */}
                    {on ? (next ? `On · next ${new Date(next).toLocaleString()}` : 'On') : job.desc}
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={job.label}
                  data-testid={`autonomous-toggle-${job.kind}`}
                  disabled={busy}
                  onClick={() => onToggle(job.kind, !on, timezone)}
                  className={cn(
                    'relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50',
                    on ? 'bg-emerald-500' : 'bg-muted',
                  )}
                >
                  <span
                    className={cn(
                      'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all',
                      on ? 'left-[22px]' : 'left-0.5',
                    )}
                  />
                </button>
              </li>
            );
          })}

          {/* D-A3-PROACTIVE — the double-gated "Proactive check-ins" row (sets the chat opt-in AND the
              schedule together, so it can never silently no-op). Only rendered when wired. */}
          {proactive && (
            <li className="flex items-center justify-between gap-3 py-2.5" data-testid="autonomous-proactive-row">
              <div className="min-w-0">
                <div className="text-sm">Proactive check-ins</div>
                <div className="text-xs text-muted-foreground">
                  {proactive.enabled ? 'On — I may reach out when it has been a while.' : 'Let me open with a thought after a quiet stretch.'}
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={proactive.enabled}
                aria-label="Proactive check-ins"
                data-testid="autonomous-toggle-proactive_nudge"
                disabled={proactive.saving}
                onClick={() => proactive.onToggle(!proactive.enabled, timezone)}
                className={cn(
                  'relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50',
                  proactive.enabled ? 'bg-emerald-500' : 'bg-muted',
                )}
              >
                <span
                  className={cn(
                    'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all',
                    proactive.enabled ? 'left-[22px]' : 'left-0.5',
                  )}
                />
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
