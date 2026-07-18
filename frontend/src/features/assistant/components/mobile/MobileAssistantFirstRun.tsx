// FR (draft frame 13, "Safe defaults, stated plainly") — the assistant journal's first-run screen.
// Composes the pieces that already exist (the fail-closed capture consent from context + the
// TimezoneConfirm) UNDER a privacy promise, with the consent switch OFF by default. The point of
// the draft: safe defaults stated up front, not buried. View-only — logic lives in the context +
// useTimezone + the first-run gate (the parent passes onDone).
import { Lock, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAssistant } from '../../context/AssistantContext';
import { useTimezone } from '../../hooks/useTimezone';
import { TimezoneConfirm } from '../TimezoneConfirm';

export interface MobileAssistantFirstRunProps {
  onDone: () => void;
}

export function MobileAssistantFirstRun({ onDone }: MobileAssistantFirstRunProps) {
  const { consentEnabled, consentSaving, setConsent, projectId } = useAssistant();
  const tz = useTimezone();

  return (
    <div className="mx-auto flex h-full w-full max-w-lg flex-col gap-4 overflow-y-auto p-5" data-testid="assistant-first-run">
      <div>
        <h1 className="font-serif text-2xl leading-tight text-balance">
          A private journal that remembers for you.
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Talk through your day. It quietly notices the people, projects and decisions — and only
          what you keep becomes your journal.
        </p>
      </div>

      {/* The privacy promise LEADS (draft fix: it was a footnote before). */}
      <div className="rounded-xl border border-transparent bg-accent/10 p-3" data-testid="first-run-privacy">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-accent-foreground">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Private to you. Encrypted on your device. Erasable in one tap.
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Nothing is captured, saved, or put on your lock screen until you choose it.
        </p>
      </div>

      {/* Capture consent — OFF by default (fail-closed). The one control the draft foregrounds. */}
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
        <div className="min-w-0">
          <div className="text-sm font-medium">Notice things as we talk</div>
          <div className="text-xs text-muted-foreground">
            {consentEnabled ? 'On — people & projects are noticed.' : 'Off until you turn it on — nothing is noticed before that.'}
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={consentEnabled}
          aria-label="Notice things as we talk"
          data-testid="first-run-consent"
          disabled={consentSaving || !projectId}
          onClick={() => setConsent(!consentEnabled)}
          className={cn(
            'relative h-7 w-12 shrink-0 rounded-full transition disabled:opacity-50',
            consentEnabled ? 'bg-emerald-500' : 'bg-muted',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all',
              consentEnabled ? 'left-[22px]' : 'left-0.5',
            )}
          />
        </button>
      </div>

      {/* Time-zone confirm feeds correct day-bucketing (only until the user has set a zone). */}
      {tz.needsConfirm && (
        <div className="rounded-xl border border-border bg-card p-3">
          <TimezoneConfirm detected={tz.detected} saving={tz.saving} onConfirm={tz.confirm} />
        </div>
      )}

      <div className="mt-auto flex items-center gap-1.5 pt-2 text-[11px] text-muted-foreground">
        <Lock className="h-3 w-3" aria-hidden="true" /> You can turn capture off, forget anyone, or erase everything anytime.
      </div>
      <button
        type="button"
        data-testid="first-run-start"
        onClick={onDone}
        className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
      >
        Start my first day
      </button>
    </div>
  );
}
