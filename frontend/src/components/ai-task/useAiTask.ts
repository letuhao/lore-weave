import { useCallback, useRef, useState } from 'react';
import { readBackendError } from '@/lib/readBackendError';

// AI-Task Standard — the SYNC-INLINE propose→review→confirm controller for one-shot
// generate dialogs (schema-propose, bio-regen, polish, quality…). Owns busy / error
// / result so each dialog stops re-deriving the try/catch/readBackendError/setBusy
// boilerplate. Errors are read through the ONE shared reader (WHY, not "Bad Gateway").

interface Options<Cfg, Res> {
  /** Produce the reviewable result (the "propose"/"run" call). */
  run: (cfg: Cfg) => Promise<Res>;
  /** Commit the reviewed result (the "adopt"/"apply" call). Optional. */
  confirm?: (result: Res) => Promise<void>;
  /** Side-channel for a toast, etc. `error` is also exposed for inline display. */
  onError?: (message: string) => void;
}

export interface AiTask<Cfg, Res> {
  result: Res | null;
  busy: boolean;
  error: string | null;
  /** Run the task; returns the result (or null on failure — never throws). */
  run: (cfg: Cfg) => Promise<Res | null>;
  /** Commit the current result; re-throws so the dialog can stay open on failure. */
  confirm: () => Promise<void>;
  /** Clear result + error (e.g. "regenerate" / dialog re-open). */
  reset: () => void;
  setResult: (r: Res | null) => void;
}

export function useAiTask<Cfg, Res>(options: Options<Cfg, Res>): AiTask<Cfg, Res> {
  const [result, setResult] = useState<Res | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Keep the latest callbacks without re-creating run/confirm each render.
  const opts = useRef(options);
  opts.current = options;

  const run = useCallback(async (cfg: Cfg): Promise<Res | null> => {
    setBusy(true);
    setError(null);
    try {
      const r = await opts.current.run(cfg);
      setResult(r);
      return r;
    } catch (e) {
      const msg = readBackendError(e);
      setError(msg);
      opts.current.onError?.(msg);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const confirm = useCallback(async (): Promise<void> => {
    const current = result;
    if (current == null || !opts.current.confirm) return;
    setBusy(true);
    setError(null);
    try {
      await opts.current.confirm(current);
    } catch (e) {
      const msg = readBackendError(e);
      setError(msg);
      opts.current.onError?.(msg);
      throw e; // dialog stays open
    } finally {
      setBusy(false);
    }
  }, [result]);

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return { result, busy, error, run, confirm, reset, setResult };
}
