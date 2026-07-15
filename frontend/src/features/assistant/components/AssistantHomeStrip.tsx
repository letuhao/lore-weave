// WS-1.10 view — the assistant home strip (right rail): greeting, the capture-consent chip, the
// "today so far" rail, and the "End my day" → review flow. Composition only; all logic is in the
// context + the two controller hooks (CLAUDE.md MVC).
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { useAssistant } from '../context/AssistantContext';
import { useCaptureRail } from '../hooks/useCaptureRail';
import { useDiaryFactInbox } from '../hooks/useDiaryFactInbox';
import { useReflection } from '../hooks/useReflection';
import { useScorecards } from '../hooks/useScorecards';
import { useTimezone } from '../hooks/useTimezone';
import { CaptureRail } from './CaptureRail';
import { CoachingScorecard } from './CoachingScorecard';
import { DiaryFactInbox } from './DiaryFactInbox';
import { EndOfDayReview } from './EndOfDayReview';
import { ReflectionCard } from './ReflectionCard';
import { TimezoneConfirm } from './TimezoneConfirm';

export function AssistantHomeStrip() {
  const { user } = useAuth();
  const { bookId, projectId, consentEnabled, consentSaving, setConsent, endOfDay: eod } = useAssistant();
  const rail = useCaptureRail(bookId);
  const inbox = useDiaryFactInbox();
  const reflection = useReflection(bookId);
  const scorecards = useScorecards();
  const tz = useTimezone();

  const firstName = (user?.display_name || user?.email || '').split(/[ @]/)[0];

  return (
    <aside className="flex h-full w-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold" data-testid="assistant-greeting">
          Welcome back{firstName ? `, ${firstName}` : ''}
        </h2>
        <p className="text-sm text-muted-foreground">Your private work assistant.</p>
      </div>

      {/* F2 — confirm the local time zone (once) so the distiller buckets each day correctly. */}
      {tz.needsConfirm && <TimezoneConfirm detected={tz.detected} saving={tz.saving} onConfirm={tz.confirm} />}

      {/* Work-capture consent (A2, fail-closed). Explicit opt-in — never auto-enabled. */}
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-3">
        <div className="min-w-0">
          <div className="text-sm font-medium">
            {consentEnabled ? 'Capturing your work notes' : 'Capture is off'}
          </div>
          <div className="text-xs text-muted-foreground">
            {consentEnabled
              ? 'People & projects are noticed as you talk.'
              : 'Turn on to remember colleagues, projects and decisions.'}
          </div>
        </div>
        <button
          type="button"
          data-testid="assistant-consent-toggle"
          role="switch"
          aria-checked={consentEnabled}
          disabled={consentSaving || !projectId}
          onClick={() => setConsent(!consentEnabled)}
          className={cn(
            'relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50',
            consentEnabled ? 'bg-emerald-500' : 'bg-muted',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all',
              consentEnabled ? 'left-[22px]' : 'left-0.5',
            )}
          />
        </button>
      </div>

      <div className="flex items-center justify-between">
        <span className="sr-only">Captured items</span>
        <button
          type="button"
          data-testid="assistant-refresh-rail"
          onClick={() => void rail.refresh()}
          className="ml-auto text-xs text-muted-foreground underline-offset-2 hover:underline"
        >
          Refresh
        </button>
      </div>
      <CaptureRail entities={rail.entities} loading={rail.loading} captureOn={consentEnabled} />

      <button
        type="button"
        data-testid="assistant-end-day"
        disabled={eod.status === 'distilling'}
        onClick={() => {
          // End-the-day distills the day AND diverts its facts to the inbox, so refresh both surfaces.
          void eod.trigger().then(() => inbox.refetch());
          void rail.refresh();
        }}
        className="rounded-md border border-border bg-secondary px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {eod.status === 'distilling' ? 'Ending your day…' : 'End my day'}
      </button>

      <EndOfDayReview
        status={eod.status}
        entry={eod.entry}
        error={eod.error}
        keeping={eod.keeping}
        onKeep={eod.keep}
      />

      {/* C8 / WS-5.3 — the latest weekly reflection draft + dismissable patterns (server is SoT). */}
      {reflection.reflection && (
        <ReflectionCard
          reflection={reflection.reflection}
          patterns={reflection.patterns}
          onDismiss={reflection.dismiss}
        />
      )}

      {/* R2 / SD-C8 — the latest coaching scorecard (quarantine badge; SD-7 keeps it shown-never-trended). */}
      {scorecards.latest && <CoachingScorecard card={scorecards.latest.card} />}

      {/* WS-2.5 — the diary fact inbox: keep/dismiss the facts the distiller diverted for review. */}
      <DiaryFactInbox
        facts={inbox.facts}
        isLoading={inbox.isLoading}
        error={inbox.error}
        pendingId={inbox.pendingId}
        onConfirm={inbox.confirm}
        onReject={inbox.reject}
      />
    </aside>
  );
}
