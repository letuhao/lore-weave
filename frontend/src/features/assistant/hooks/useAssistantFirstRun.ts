// FR (draft frame 13) — the assistant JOURNAL first-run gate. Distinct from the app-level intent
// fork (`hasSeenOnboarding`): a user can pick the "assistant" intent without ever seeing the
// journal's first-run, so this is its own server pref (multi-device, NOT localStorage — the same
// /v1/me/preferences store the onboarding fork uses). Shows the safe-defaults screen once.
import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';

export const ASSISTANT_FIRST_RUN_PREF_KEY = 'assistantFirstRunDone';

type State = 'loading' | 'done' | 'first';

export interface AssistantFirstRun {
  /** True while the flag is still loading — avoid a flash of the first-run screen. */
  isLoading: boolean;
  /** Show the first-run screen iff this account has never completed it. */
  shouldShow: boolean;
  /** Mark it done (server write-through, multi-device) — the normal assistant renders next. */
  markDone: () => void;
}

export function useAssistantFirstRun(): AssistantFirstRun {
  const { accessToken } = useAuth();
  const [state, setState] = useState<State>('loading');

  // Synchronization (loading the persisted flag) — a legitimate useEffect (not an event reaction).
  useEffect(() => {
    if (!accessToken) {
      setState('loading');
      return;
    }
    let cancelled = false;
    void loadPrefFromServer<boolean>(ASSISTANT_FIRST_RUN_PREF_KEY, accessToken).then((flag) => {
      if (!cancelled) setState(flag === true ? 'done' : 'first');
    });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const markDone = () => {
    // Write-through (server SSOT); the local flip is immediate so the screen closes at once.
    syncPrefsToServer(ASSISTANT_FIRST_RUN_PREF_KEY, true, accessToken);
    setState('done');
  };

  return { isLoading: state === 'loading', shouldShow: state === 'first', markDone };
}
