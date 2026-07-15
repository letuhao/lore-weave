// M5 (D-MOB-4) view — the notifications toggle. Shows an EFFECTIVE on/off (§8-S4); never renders a
// control the platform can't honour (§8-S3): unsupported → nothing; iOS-not-installed → an "Add to
// Home Screen" hint; permission-denied → a disabled row with a settings hint. View only — logic is
// in usePushSubscription. Copy states plainly that lock-screen alerts are content-free.
import { cn } from '@/lib/utils';
import { usePushSubscription } from './usePushSubscription';

export function PushToggle() {
  const { capability, enabled, busy, enable, disable } = usePushSubscription();

  if (!capability.supported) return null;

  if (capability.iosNeedsInstall) {
    return (
      <div className="rounded-lg border border-border bg-card p-3" data-testid="push-ios-hint">
        <div className="text-sm font-medium">Get nudges when you&apos;re away</div>
        <div className="text-xs text-muted-foreground">
          Add LoreWeave to your Home Screen to receive notifications on iOS.
        </div>
      </div>
    );
  }

  const denied = capability.permission === 'denied';

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3">
      <div className="min-w-0">
        <div className="text-sm font-medium">Notifications</div>
        <div className="text-xs text-muted-foreground">
          {denied
            ? 'Blocked — enable notifications for LoreWeave in your device settings.'
            : 'A gentle buzz when your assistant or a job needs you. Lock-screen text never shows your notes.'}
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label="Notifications"
        data-testid="push-toggle"
        disabled={busy || denied}
        onClick={() => (enabled ? disable() : enable())}
        className={cn(
          'relative h-7 w-12 shrink-0 rounded-full transition disabled:opacity-50',
          enabled ? 'bg-emerald-500' : 'bg-muted',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all',
            enabled ? 'left-[22px]' : 'left-0.5',
          )}
        />
      </button>
    </div>
  );
}
