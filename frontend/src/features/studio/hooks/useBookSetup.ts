// Part B — "Set up this book": the one explicit action that satisfies BOTH prerequisites at once so
// every Story-Bible surface lights up together (kills the "Work but no plan" half-set-up state). It
// REUSES the existing idempotent create-arc + ensure-Work origin (usePlanOrigin) — a first structure
// node plus the knowledge Work — rather than re-solving either.
//
// Sealed (B2): this is OPT-IN, never auto-run — a prose-first writer who only wants references keeps
// the narrow single-prerequisite door (WorkSetupCta) as the primary; this is the secondary shortcut.
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { usePlanOrigin } from '@/features/plan-hub/hooks/usePlanOrigin';

export interface BookSetup {
  /** Create the book's first structure node + ensure its Work. Null while there's no token. */
  setUp: (() => void) | null;
  busy: boolean;
}

export function useBookSetup(bookId: string, token: string | null): BookSetup {
  const { t } = useTranslation('studio');
  const origin = usePlanOrigin(bookId, token);
  const firstTitle = t('setup.firstStructureTitle', { defaultValue: 'Act One' });
  const setUp = useCallback(() => {
    void origin.start(firstTitle);
  }, [origin, firstTitle]);
  return { setUp: token ? setUp : null, busy: origin.creating };
}
