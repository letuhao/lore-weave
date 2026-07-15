// M1 (mobile) container — the assistant's bottom action dock + its sheets. Binds the SAME
// controller hooks the desktop home strip uses (useCaptureRail / useEndOfDay / useReflection /
// useScorecards / useTimezone / useDiaryFactInbox + the assistant context) exactly ONCE, and
// hands their results to the presentational sheets. Rendered only under the mobile chrome, so
// there is no double-fetch against the desktop strip (which is not mounted on mobile).
//
// The dock is the thumb-zone: "End my day" is a VISIBLE primary button (not a buried gesture —
// the drafts' rev.2 fix), and "Today"/"Journal" open addressable sheets (?sheet=…) so a deep
// link or the hardware Back button behaves correctly (MB4).
import { NotebookPen, CalendarCheck, BookText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSheetRoute } from '@/components/shared/Sheet';
import { useAssistant } from '../../context/AssistantContext';
import { useCaptureRail } from '../../hooks/useCaptureRail';
import { useDiaryEntries } from '../../hooks/useDiaryEntries';
import { useDiaryFactInbox } from '../../hooks/useDiaryFactInbox';
import { useReflection } from '../../hooks/useReflection';
import { useScorecards } from '../../hooks/useScorecards';
import { useTimezone } from '../../hooks/useTimezone';
import { MobileTodaySheet, TODAY_SHEET_ID } from './MobileTodaySheet';
import { MobileJournalSheet, JOURNAL_SHEET_ID } from './MobileJournalSheet';

export function MobileAssistantDock() {
  const { bookId, projectId, consentEnabled, consentSaving, setConsent, endOfDay: eod } = useAssistant();
  const { openSheet } = useSheetRoute();

  const rail = useCaptureRail(bookId);
  const inbox = useDiaryFactInbox();
  const reflection = useReflection(bookId);
  const scorecards = useScorecards();
  const tz = useTimezone();
  const journal = useDiaryEntries(bookId);

  // A small "needs your attention" count for the Today button: captured drafts + facts to review.
  const todayCount = rail.entities.length + inbox.facts.length;
  const distilling = eod.status === 'distilling';

  const handleEndDay = () => {
    // End the day distills AND diverts facts to the inbox, so refresh both surfaces; then open
    // Today so the user sees the review flow (mirrors the desktop strip's handler).
    void eod.trigger().then(() => inbox.refetch());
    void rail.refresh();
    openSheet(TODAY_SHEET_ID);
  };

  return (
    <div
      className="flex items-stretch gap-2 border-t border-border bg-background p-2"
      data-testid="mobile-assistant-dock"
    >
      <DockButton
        testid="dock-today"
        icon={NotebookPen}
        label="Today"
        badge={todayCount > 0 ? todayCount : undefined}
        onClick={() => openSheet(TODAY_SHEET_ID)}
      />

      <button
        type="button"
        data-testid="dock-end-day"
        disabled={distilling}
        onClick={handleEndDay}
        className={cn(
          'flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium transition-colors',
          'bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50',
        )}
      >
        <CalendarCheck className="h-5 w-5" aria-hidden="true" />
        {distilling ? 'Ending your day…' : 'End my day'}
      </button>

      <DockButton
        testid="dock-journal"
        icon={BookText}
        label="Journal"
        onClick={() => {
          void journal.refresh();
          openSheet(JOURNAL_SHEET_ID);
        }}
      />

      {/* Addressable sheets (portaled; open iff ?sheet=<id>). */}
      <MobileTodaySheet
        consentEnabled={consentEnabled}
        consentSaving={consentSaving}
        projectId={projectId}
        onSetConsent={setConsent}
        tz={tz}
        rail={rail}
        eod={eod}
        reflection={reflection}
        scorecard={scorecards.latest?.card ?? null}
        inbox={inbox}
      />
      <MobileJournalSheet entries={journal.entries} loading={journal.loading} error={journal.error} />
    </div>
  );
}

function DockButton({
  testid,
  icon: Icon,
  label,
  badge,
  onClick,
}: {
  testid: string;
  icon: React.ElementType;
  label: string;
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testid}
      aria-label={label}
      onClick={onClick}
      className="relative flex min-h-[44px] min-w-[64px] flex-col items-center justify-center gap-0.5 rounded-md border border-border text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
    >
      <Icon className="h-5 w-5" aria-hidden="true" />
      {label}
      {badge !== undefined && (
        <span
          className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground"
          aria-label={`${badge} to review`}
        >
          {badge}
        </span>
      )}
    </button>
  );
}
