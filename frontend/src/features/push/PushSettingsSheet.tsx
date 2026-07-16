// DF5 view — the notifications settings sheet (addressable ?sheet=notifications). Matches the draft:
// a VALUE-FIRST ask when push is off (say what you'll get + the content-free promise BEFORE asking
// for permission, §8-S4), and PER-CATEGORY toggles when it's on. Never shows a control the platform
// can't honour (S3). View only — logic in usePushSubscription + usePushPreferences.
import { Bell, Sparkles, ListChecks, CreditCard, Users, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Sheet, useSheetRoute } from '@/components/shared/Sheet';
import { usePushSubscription } from './usePushSubscription';
import { usePushPreferences } from './usePushPreferences';

export const NOTIFICATIONS_SHEET_ID = 'notifications';

// The pushable topics (the in-app-only `system` topic is not shown here). Order = most-valuable first.
const TOPICS: { key: string; label: string; icon: React.ElementType }[] = [
  { key: 'assistant_weekly', label: 'Weekly reflection', icon: Sparkles },
  { key: 'assistant_endofday', label: 'Daily check-in', icon: Bell },
  { key: 'jobs', label: 'Finished tasks', icon: ListChecks },
  { key: 'billing', label: 'Usage & spend', icon: CreditCard },
  { key: 'mcp_approval', label: 'Approvals', icon: ShieldCheck },
  { key: 'social', label: 'Social', icon: Users },
];

export function PushSettingsSheet() {
  const { capability, enabled, busy, enable, disable } = usePushSubscription();
  const prefs = usePushPreferences();

  return (
    <Sheet id={NOTIFICATIONS_SHEET_ID} title="Notifications" description="A gentle buzz when it matters — never your notes.">
      <div className="flex flex-col gap-4" data-testid="push-settings">
        {!capability.supported ? (
          <p className="text-sm text-muted-foreground">Notifications aren&apos;t available on this browser.</p>
        ) : capability.iosNeedsInstall ? (
          <p className="text-sm text-muted-foreground">Add LoreWeave to your Home Screen to receive notifications on iOS.</p>
        ) : !enabled ? (
          // VALUE-FIRST ask — say what you'll get + what you won't, THEN offer to turn on.
          <div data-testid="push-value-ask">
            <p className="text-sm font-medium">Want a nudge when it matters?</p>
            <ul className="mt-2 flex flex-col gap-1.5 text-sm text-muted-foreground">
              <ValuePoint icon={Sparkles}>Your weekly reflection, when it&apos;s ready</ValuePoint>
              <ValuePoint icon={ListChecks}>A translation or import finishing</ValuePoint>
              <ValuePoint icon={ShieldCheck}>Lock-screen text never shows your notes</ValuePoint>
            </ul>
            {capability.permission === 'denied' ? (
              <p className="mt-3 text-xs text-muted-foreground">Blocked — enable notifications for LoreWeave in your device settings.</p>
            ) : (
              <button
                type="button"
                data-testid="push-turn-on"
                disabled={busy}
                onClick={enable}
                className="mt-3 flex min-h-[44px] w-full items-center justify-center rounded-xl bg-primary text-sm font-semibold text-primary-foreground disabled:opacity-50"
              >
                Turn on
              </button>
            )}
          </div>
        ) : (
          // ON — per-category toggles + the master "this device" control.
          <>
            <div className="flex items-center justify-between rounded-lg border border-border bg-card p-3">
              <div className="min-w-0">
                <div className="text-sm font-medium">On this device</div>
                <div className="text-xs text-muted-foreground">Signing out also removes this device.</div>
              </div>
              <ToggleSwitch checked={enabled} disabled={busy} onChange={() => disable()} label="Notifications on this device" />
            </div>

            <div>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">What to buzz for</h3>
              <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-card">
                {TOPICS.map((t) => {
                  const on = prefs.topics[t.key] ?? false;
                  return (
                    <div key={t.key} className="flex items-center gap-3 border-b border-border px-3 py-2.5 last:border-b-0">
                      <t.icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                      <span className="flex-1 text-sm">{t.label}</span>
                      <ToggleSwitch
                        checked={on}
                        disabled={prefs.isLoading}
                        onChange={() => prefs.setTopic(t.key, !on)}
                        label={t.label}
                        testid={`push-topic-${t.key}`}
                      />
                    </div>
                  );
                })}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Lock-screen alerts are always content-free — they never show your notes.</p>
            </div>
          </>
        )}
      </div>
    </Sheet>
  );
}

function ValuePoint({ icon: Icon, children }: { icon: React.ElementType; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2">
      <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      {children}
    </li>
  );
}

function ToggleSwitch({
  checked,
  disabled,
  onChange,
  label,
  testid,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  label: string;
  testid?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      data-testid={testid}
      disabled={disabled}
      onClick={onChange}
      className={cn('relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50', checked ? 'bg-emerald-500' : 'bg-muted')}
    >
      <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', checked ? 'left-[22px]' : 'left-0.5')} />
    </button>
  );
}
