// FR / D17 controller — "Erase everything": the whole-account erasure primitive. CLAUDE.md MVC:
// the destructive call + its in-flight state live here; the memory view renders the worded confirm
// and calls `erase()`. The BFF's DELETE /v1/assistant/data cascades chat + knowledge + the diary
// book (owner-derived from the JWT). Irreversible — the view MUST confirm first.
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';

export function useEraseAllData() {
  const { accessToken } = useAuth();
  const [erasing, setErasing] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const erase = useCallback(async (): Promise<boolean> => {
    if (!accessToken) return false;
    setErasing(true);
    try {
      const res = await assistantApi.eraseAllData(accessToken);
      if (res.erased) {
        toast.success('Everything is erased — your memory and journal are gone.');
        return true;
      }
      toast.error('Nothing was erased. Please try again.');
      return false;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not erase your data.');
      return false;
    } finally {
      if (mounted.current) setErasing(false);
    }
  }, [accessToken]);

  return { erase, erasing };
}
