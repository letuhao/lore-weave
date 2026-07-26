// A4 (WS-2.10 / T18) controller — "I changed jobs / start a new chapter". Closes the current assistant
// epoch (archives it + invalidates its facts so the ex-employer's memory leaves default recall) and mints
// a fresh project. CLAUDE.md MVC: the call + its in-flight state live here; the view renders the worded
// confirm and calls `startNewEpoch()`. Not a delete (archived, recoverable by admin) — but it changes
// what recall sees, so the view MUST confirm first.
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { NewEpochResult } from '../types';

export function useNewEpoch(bookId: string | null) {
  const { accessToken } = useAuth();
  const [starting, setStarting] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const startNewEpoch = useCallback(async (): Promise<NewEpochResult | null> => {
    if (!accessToken || !bookId) return null;
    setStarting(true);
    try {
      const res = await assistantApi.newEpoch(accessToken, { book_id: bookId });
      if (res.epoch_closed) {
        const n = res.facts_invalidated ?? 0;
        toast.success(`New chapter started — ${n} mem${n === 1 ? 'ory' : 'ories'} from before are set aside.`);
      } else {
        toast.error('Could not start a new chapter. Please try again.');
      }
      return res;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not start a new chapter.');
      return null;
    } finally {
      if (mounted.current) setStarting(false);
    }
  }, [accessToken, bookId]);

  return { startNewEpoch, starting };
}
