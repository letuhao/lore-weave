// D0 (S6) — the Studio Work-creation CTA.
//
// Every S6 quality panel gates on a composition Work (`useQualityWork` → `no-work`). The GUI-only
// affordance that CREATES one — `useCreateWork` / `usePendingWorkResolver` / `useGuidedFirstRun` —
// was mounted ONLY on the legacy `CompositionPanel`, so a GUI-only user in the Studio hit `no-work`
// with no self-service exit (their only options were to talk to the agent or leave for /edit). This
// CTA lives in the shared no-work gate and REUSES the existing create + knowledge-backfill-poll hooks.
//
// `POST /books/{id}/work` is idempotent + race-safe (works.py:12 "get-or-create … idempotent";
// `_ensure_pending_work` is capped at one per book by a partial-unique index) — so a duplicate click,
// or a click on a book that already has a Work, NEVER mints a second one. It just resolves the Work.
//
// Pending path (D-C16): if a greenfield Work is created while knowledge-service is down, its
// `project_id` is null and the resolveWork query can't surface it; we hold the surrogate `id` and let
// `usePendingWorkResolver` poll resolve-project until the knowledge project is backfilled, then the
// work query invalidates and the gate flips to `ready`.
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useCreateWork, usePendingWorkResolver } from '@/features/composition/hooks/useWork';

export function WorkSetupCta({ bookId, token }: { bookId: string; token: string | null }) {
  const { t } = useTranslation('studio');
  const create = useCreateWork(bookId, token);
  const resolver = usePendingWorkResolver(bookId, token);
  const busy = create.isPending || resolver.state === 'resolving';

  const onSetup = async () => {
    try {
      const work = await create.mutateAsync();
      // Greenfield Work created during a knowledge outage → project_id null. Poll to backfill; the
      // resolver invalidates the work query on success. Otherwise useCreateWork.onSuccess already did.
      if (!work.project_id && work.id) resolver.start(work.id);
    } catch {
      toast.error(t('quality.setupWorkError', { defaultValue: 'Could not set up the co-writer. Try again.' }));
    }
  };

  // The backfill poll gave up (knowledge still down after the attempt cap) — offer a retry, never a
  // silent stall. This is an ERROR the user can act on, not an empty state.
  if (resolver.state === 'failed') {
    return (
      <div data-testid="work-setup-failed" className="flex flex-col items-center gap-2">
        <p className="max-w-xs text-xs text-amber-700 dark:text-amber-300">
          {t('quality.setupWorkPending', {
            defaultValue: 'Your co-writer session was created but its knowledge project is still being set up. Try again shortly.',
          })}
        </p>
        <button
          type="button"
          data-testid="work-setup-retry"
          onClick={() => resolver.retry()}
          className="rounded bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
        >
          {t('quality.setupWorkRetry', { defaultValue: 'Retry' })}
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      data-testid="work-setup-cta"
      onClick={onSetup}
      disabled={busy}
      className="rounded bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
    >
      {busy
        ? t('quality.settingUpWork', { defaultValue: 'Setting up…' })
        : t('quality.setupWork', { defaultValue: 'Set up co-writer' })}
    </button>
  );
}
