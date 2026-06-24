import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth';
import { loadPrefFromServer, savePrefToServer, syncPrefsToServer } from '@/lib/syncPrefs';
import { routeForIntent } from '../lib/intentRoutes';
import { ONBOARDING_SEEN_PREF_KEY, type IntentId } from '../types';

type SeenState = 'loading' | 'seen' | 'unseen';

/** Durable (awaited) write-through of the seen-flag — used before navigating. */
function persistSeen(token: string | null | undefined): Promise<boolean> {
  return savePrefToServer(ONBOARDING_SEEN_PREF_KEY, true, token);
}

// C22 — onboarding controller (FE MVC: this hook owns ALL logic, the view only
// renders). Two responsibilities:
//  1. First-run GATING — read the server-side seen-flag (multi-device; NOT
//     localStorage-only) so the fork shows once per account, not every session.
//  2. Intent CHOICE — on pick, mark seen (server write-through) and navigate to
//     the tailored surface via an EXPLICIT handler (no useEffect-for-events).
//
// `forceShow` (re-entry: the /onboarding "start something new" route) renders the
// screen regardless of the seen-flag without re-fetching it.
export function useOnboarding(options?: { forceShow?: boolean }) {
  const forceShow = options?.forceShow ?? false;
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [seen, setSeen] = useState<SeenState>(forceShow ? 'unseen' : 'loading');

  // Synchronization (loading the persisted flag) is a legitimate useEffect use —
  // it is NOT reacting to a user action. Re-entry skips the fetch entirely.
  useEffect(() => {
    if (forceShow) return;
    let cancelled = false;
    if (!accessToken) {
      setSeen('loading');
      return;
    }
    void loadPrefFromServer<boolean>(ONBOARDING_SEEN_PREF_KEY, accessToken).then((flag) => {
      if (cancelled) return;
      setSeen(flag === true ? 'seen' : 'unseen');
    });
    return () => {
      cancelled = true;
    };
  }, [accessToken, forceShow]);

  /** Persist the seen-flag server-side (write-through; multi-device). */
  const markSeen = () => {
    syncPrefsToServer(ONBOARDING_SEEN_PREF_KEY, true, accessToken);
    setSeen('seen');
  };

  // Explicit choice handler: persist seen server-side, THEN route to the tailored
  // surface. We await the durable write first so the multi-device guarantee holds
  // in the common case (a returning user / another device skips the fork); the
  // write tolerates failure (the only degradation is the fork re-showing once),
  // so navigation always proceeds. This is an explicit handler — NOT a useEffect
  // reaction to a state change.
  const chooseIntent = (id: IntentId) => {
    const route = routeForIntent(id);
    void persistSeen(accessToken).finally(() => {
      setSeen('seen');
      navigate(route);
    });
  };

  return {
    /** True while the seen-flag is still loading (avoid a flash of the screen). */
    isLoading: seen === 'loading',
    /** Show the intent screen iff re-entry OR a first run that hasn't been seen. */
    shouldShow: forceShow || seen === 'unseen',
    chooseIntent,
    markSeen,
  };
}
