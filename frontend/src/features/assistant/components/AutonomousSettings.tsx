// A3 view — "{t('autonomous.title')}". The opt-in controls that ARM the (previously dormant)
// autonomous jobs. Each toggle is fail-closed OFF and shows its EFFECTIVE state (on/off + the next run),
// never a hidden default. View-only — the read/write logic lives in useAssistantSchedule.
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { AutonomousJobKind } from '../types';

interface JobMeta {
  kind: AutonomousJobKind;
  labelKey: string;
  descKey: string;
}

// The schedule-only set (each fully delivered by arming its schedule row alone). `proactive_nudge` is NOT
// here — it's double-gated (chat opt-in + schedule), so it gets a DEDICATED row via the `proactive` prop
// (wired to useProactiveSetting, which sets both). Order = most-valuable first.
const JOBS: JobMeta[] = [
  { kind: 'eod_distill', labelKey: 'autonomous.eod', descKey: 'autonomous.eodDesc' },
  { kind: 'weekly_reflection', labelKey: 'autonomous.weeklyReflection', descKey: 'autonomous.weeklyReflectionDesc' },
  { kind: 'weekly_rollup', labelKey: 'autonomous.weeklySummary', descKey: 'autonomous.weeklySummaryDesc' },
  { kind: 'nudge', labelKey: 'autonomous.reminders', descKey: 'autonomous.remindersDesc' },
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
  const { t } = useTranslation('assistant');
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3" data-testid="autonomous-settings">
      <div>
        <div className="text-sm font-medium">{t('autonomous.title')}</div>
        <div className="text-xs text-muted-foreground">
          {t('autonomous.description')}
        </div>
      </div>

      {loading ? (
        <p className="py-2 text-xs text-muted-foreground" >{t('autonomous.loading')}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {JOBS.map((job) => {
            const on = isEnabled(job.kind);
            const busy = savingKind === job.kind;
            const next = on ? nextFireAt(job.kind) : null;
            return (
              <li key={job.kind} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="text-sm">{t(job.labelKey)}</div>
                  <div className="text-xs text-muted-foreground">
                    {/* Effective state, stated plainly (SET rule: never a hidden default). */}
                    {on ? (next ? t('autonomous.next', { time: new Date(next).toLocaleString() }) : t('autonomous.on')) : t(job.descKey)}
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={t(job.labelKey)}
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
                <div className="text-sm">{t('autonomous.proactive')}</div>
                <div className="text-xs text-muted-foreground">
                  {proactive.enabled ? t('autonomous.proactiveOn') : t('autonomous.proactiveOff')}
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={proactive.enabled}
                aria-label={t('autonomous.proactive')}
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
