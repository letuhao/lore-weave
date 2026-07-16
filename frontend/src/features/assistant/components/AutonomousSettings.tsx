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

// The user-facing set. Order = most-valuable first (auto-journal is the headline autonomous behavior).
// NOTE (A3 review): `proactive_nudge` is deliberately NOT here. Arming its schedule is only HALF the
// control — chat's proactive-turn seam ALSO fail-closed-gates on a separate `assistant.proactive_enabled`
// setting (default OFF) that has no FE yet, so a "Proactive check-ins" toggle would appear ON and silently
// do nothing (the no-silent-no-op rule). Exposing it waits until its full setting chain is wired
// (D-A3-PROACTIVE-SETTING). The four below are fully delivered by the schedule alone.
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
}

export function AutonomousSettings({ loading, isEnabled, nextFireAt, savingKind, timezone, onToggle }: AutonomousSettingsProps) {
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
        </ul>
      )}
    </section>
  );
}
