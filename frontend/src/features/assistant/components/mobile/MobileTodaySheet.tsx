// M1 (mobile) view — the "Today" sheet: the assistant home strip's content, re-laid-out for
// a phone (full-width cards, thumb reach) but built ENTIRELY from the existing presentational
// cards (CaptureRail, EndOfDayReview, ReflectionCard, CoachingScorecard, DiaryFactInbox,
// TimezoneConfirm). View only — every prop comes from the dock's reused hooks (CLAUDE.md MVC).
import { cn } from '@/lib/utils';
import { Sheet } from '@/components/shared/Sheet';
import type { GlossaryEntitySummary } from '@/features/glossary/types';
import type { DiaryEntry, DiaryPendingFact, ReflectionPattern, Scorecard } from '../../types';
import type { EndOfDayStatus } from '../../hooks/useEndOfDay';
import { CaptureRail } from '../CaptureRail';
import { CoachingScorecard } from '../CoachingScorecard';
import { DiaryFactInbox } from '../DiaryFactInbox';
import { EndOfDayReview } from '../EndOfDayReview';
import { ReflectionCard } from '../ReflectionCard';
import { TimezoneConfirm } from '../TimezoneConfirm';

export const TODAY_SHEET_ID = 'today';

export interface MobileTodaySheetProps {
  // consent (fail-closed — defaults OFF, from the assistant context)
  consentEnabled: boolean;
  consentSaving: boolean;
  projectId: string | null;
  onSetConsent: (enabled: boolean) => void;
  // timezone confirm (F2)
  tz: { needsConfirm: boolean; detected: string; saving: boolean; confirm: (tz: string) => void };
  // capture rail
  rail: { entities: GlossaryEntitySummary[]; loading: boolean; refresh: () => void };
  // end-of-day
  eod: { status: EndOfDayStatus; entry: DiaryEntry | null; error: string | null; keeping: boolean; keep: () => void };
  // weekly reflection + dismissable chips (R1)
  reflection: { reflection: DiaryEntry | null; patterns: ReflectionPattern[]; dismiss: (patternKey: string) => Promise<void> };
  // coaching scorecard (R2 — quarantine badge lives in the card; SD-7 shown-never-trended)
  scorecard: Scorecard | null;
  // diary fact inbox (WS-2.5)
  inbox: {
    facts: DiaryPendingFact[];
    isLoading: boolean;
    error: Error | null;
    pendingId: string | null;
    confirm: (id: string) => void;
    reject: (id: string) => void;
  };
}

export function MobileTodaySheet(props: MobileTodaySheetProps) {
  const { consentEnabled, consentSaving, projectId, onSetConsent, tz, rail, eod, reflection, scorecard, inbox } = props;

  return (
    <Sheet id={TODAY_SHEET_ID} title="Today" description="Your captures, review and memory for today.">
      <div className="flex flex-col gap-4">
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
            aria-label="Work-capture consent"
            disabled={consentSaving || !projectId}
            onClick={() => onSetConsent(!consentEnabled)}
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

        <CaptureRail entities={rail.entities} loading={rail.loading} captureOn={consentEnabled} />

        <EndOfDayReview
          status={eod.status}
          entry={eod.entry}
          error={eod.error}
          keeping={eod.keeping}
          onKeep={eod.keep}
        />

        {reflection.reflection && (
          <ReflectionCard
            reflection={reflection.reflection}
            patterns={reflection.patterns}
            onDismiss={reflection.dismiss}
          />
        )}

        {scorecard && <CoachingScorecard card={scorecard} />}

        <DiaryFactInbox
          facts={inbox.facts}
          isLoading={inbox.isLoading}
          error={inbox.error}
          pendingId={inbox.pendingId}
          onConfirm={inbox.confirm}
          onReject={inbox.reject}
        />
      </div>
    </Sheet>
  );
}
