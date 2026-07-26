// The two "nothing to show" states for the composition-backed quality panels
// (promises/critic/coverage), and the distinction between them is the whole point.
//
//   no-work     — a fact about the BOOK: no composition Work exists, so nothing has ever run.
//   unavailable — a fact about US: composition-service could not be reached. The data may well
//                 exist; we could not look. Saying "start composing a chapter first" here is a
//                 WRONG ANSWER dressed as a helpful nudge.
//
// All three panels used to collapse both (plus a failed query) into the no-work sentence, because
// they gated on `status !== 'found'`. Same class as the canon panel's HIGH (RUN-STATE DR-27).
// The gate that tells them apart is `useQualityWork`.
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { QualityWorkState } from './useQualityWork';
import { Skeleton } from '@/components/shared';
import { WorkSetupCta } from './WorkSetupCta';

export function QualityNoWorkState({ testId, action }: { testId: string; action?: ReactNode }) {
  const { t } = useTranslation('studio');
  return (
    <div data-testid={testId} className="flex h-full min-h-0 flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
        {t('quality.noWork', {
          defaultValue: 'This book has no co-writer session yet — set one up (or start composing a chapter), then quality data will appear here.',
        })}
      </p>
      {action}
    </div>
  );
}

/** Composition-service is unreachable. This is an ERROR, not an empty state — it must never read as
 *  "there is nothing here", and it offers the only useful action: try again. */
export function QualityUnavailableState({ testId }: { testId: string }) {
  const { t } = useTranslation('studio');
  return (
    <div data-testid={testId} className="flex h-full min-h-0 items-center justify-center p-6 text-center">
      <p className="max-w-sm text-sm text-amber-700 dark:text-amber-300">
        {t('quality.workUnavailable', {
          defaultValue: 'Could not reach the co-writer service, so this book’s quality data could not be loaded. Problems may exist that are not shown here. Try again shortly.',
        })}
      </p>
    </div>
  );
}

/** Renders the gate's non-ready states. Returns null once a Work is resolved, so a panel reads:
 *      const work = useQualityWork(host.bookId, accessToken);
 *      if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-critic" bookId={host.bookId} token={accessToken} />;
 *  and can then use `work.projectId` unconditionally.
 *
 *  D0 — when `bookId`/`token` are passed, the `no-work` branch offers a "Set up co-writer" CTA
 *  (`WorkSetupCta`) so a GUI-only user can create the Work without leaving the Studio. The CTA appears
 *  ONLY on `no-work` — NEVER on `unavailable` (composition-service is down; the data may exist and we
 *  could not look — a "set up" nudge there is a wrong answer that invites a DUPLICATE Work). */
export function QualityWorkGate({
  state, testIdPrefix, bookId, token,
}: {
  state: QualityWorkState; testIdPrefix: string; bookId?: string; token?: string | null;
}) {
  if (state.kind === 'loading') {
    return (
      <div data-testid={`${testIdPrefix}-loading`} className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (state.kind === 'unavailable') return <QualityUnavailableState testId={`${testIdPrefix}-unavailable`} />;
  if (state.kind === 'no-work') {
    return (
      <QualityNoWorkState
        testId={`${testIdPrefix}-no-work`}
        action={bookId ? <WorkSetupCta bookId={bookId} token={token ?? null} /> : undefined}
      />
    );
  }
  return null;
}
