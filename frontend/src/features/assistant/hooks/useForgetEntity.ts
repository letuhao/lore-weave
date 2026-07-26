// WS-2.6c / D17 controller — "Forget a person": the scoped-erasure primitive. CLAUDE.md MVC: the
// destructive call + its in-flight state live here; the memory view renders the confirm + calls
// `forget(name)`. Keyed by the remembered person's NAME (the BFF resolves the KG entity + facts +
// pending tombstone + redacts the diary source prose). Irreversible — the view MUST confirm first.
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { ForgetResult } from '../types';

export function useForgetEntity(bookId: string | null) {
  const { accessToken } = useAuth();
  const [forgettingName, setForgettingName] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const forget = useCallback(
    async (name: string): Promise<ForgetResult | null> => {
      const person = name.trim();
      if (!accessToken || !bookId || !person) return null;
      setForgettingName(person);
      try {
        const res = await assistantApi.forgetPerson(accessToken, { book_id: bookId, name: person });
        // Leg 1 (structured erasure) done. Leg 2 (source redaction) is non-fatal — say so honestly.
        if (res.redaction_error) {
          toast.warning(`Forgot ${person} from memory. Clearing the name from your journal is pending.`);
        } else {
          toast.success(`Forgot ${person} — the memory and the name are gone.`);
        }
        return res;
      } catch (e) {
        toast.error(e instanceof Error ? e.message : `Could not forget ${person}.`);
        return null;
      } finally {
        if (mounted.current) setForgettingName(null);
      }
    },
    [accessToken, bookId],
  );

  return { forget, forgettingName };
}
