import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { loadPrefFromServer, savePrefToServer } from '@/lib/syncPrefs';
import { STUDIO_ONBOARDING_SEEN_PREF_KEY, STUDIO_ROLE_PREF_KEY, type StudioRole } from './types';

type SeenState = 'loading' | 'seen' | 'unseen';

/**
 * Studio-scoped onboarding controller (#19 G5/G7) — gates a role-picker overlay shown above the
 * mounted StudioFrame the first time an account visits Studio, server-synced (multi-device) via
 * the same `syncPrefs` mechanism `features/onboarding/hooks/useOnboarding.ts` already uses.
 *
 * Unlike that global first-run hook, this one is never remounted per-route (the overlay lives
 * persistently above the dock), so re-showing it (the "Studio: Choose Your Focus" palette
 * command) is a local `reopen()` toggle rather than a `forceShow` mount option.
 */
export function useStudioOnboarding() {
  const { accessToken } = useAuth();
  const [seen, setSeen] = useState<SeenState>('loading');
  const [role, setRole] = useState<StudioRole | null>(null);
  const [manualOpen, setManualOpen] = useState(false);

  // Synchronization (loading the persisted flag + role) — legitimate useEffect use, not a
  // reaction to a user action.
  useEffect(() => {
    let cancelled = false;
    if (!accessToken) { setSeen('loading'); return; }
    void Promise.all([
      loadPrefFromServer<boolean>(STUDIO_ONBOARDING_SEEN_PREF_KEY, accessToken),
      loadPrefFromServer<StudioRole>(STUDIO_ROLE_PREF_KEY, accessToken),
    ]).then(([seenFlag, roleValue]) => {
      if (cancelled) return;
      setSeen(seenFlag === true ? 'seen' : 'unseen');
      setRole(roleValue ?? null);
    });
    return () => { cancelled = true; };
  }, [accessToken]);

  /** Picking a role persists BOTH the seen-flag and the role, then dismisses. */
  const chooseRole = (next: StudioRole) => {
    void Promise.all([
      savePrefToServer(STUDIO_ONBOARDING_SEEN_PREF_KEY, true, accessToken),
      savePrefToServer(STUDIO_ROLE_PREF_KEY, next, accessToken),
    ]).finally(() => {
      setSeen('seen');
      setRole(next);
      setManualOpen(false);
    });
  };

  /** Always available, even on the very first showing — this can never be a trap. Leaves
   *  `role` untouched (null on first run). */
  const skip = () => {
    void savePrefToServer(STUDIO_ONBOARDING_SEEN_PREF_KEY, true, accessToken).finally(() => {
      setSeen('seen');
      setManualOpen(false);
    });
  };

  /** Re-show on demand (palette re-trigger) — never re-flips the seen flag; only
   *  chooseRole/skip do that. */
  const reopen = () => setManualOpen(true);

  return {
    /** True while the seen-flag/role are still loading — callers (the overlay AND
     *  WelcomePanel's role-tailoring) gate on this to avoid a flash of default content. */
    isLoading: seen === 'loading',
    shouldShow: manualOpen || (seen === 'unseen' && !!accessToken),
    role,
    chooseRole,
    skip,
    reopen,
  };
}
