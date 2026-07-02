// #12 S2 — the view-side hook: open (or join) the shared handle for (type, resourceId),
// subscribe to its snapshot, release on unmount/retarget. Panels stay thin views.
import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { useStudioHost } from '../host/StudioHostProvider';
import { openJsonDocument } from './registry';
import type { DocumentHandle, DocumentSnapshot } from './types';

export interface UseJsonDocument {
  handle: DocumentHandle | null;
  snapshot: DocumentSnapshot | null;
  /** open() rejection (unknown type, provider failure) — render an error state. */
  openError: string | null;
}

export function useJsonDocument(type: string | null, resourceId: string | null): UseJsonDocument {
  const { accessToken } = useAuth();
  const { bookId } = useStudioHost();
  const [handle, setHandle] = useState<DocumentHandle | null>(null);
  const [snapshot, setSnapshot] = useState<DocumentSnapshot | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const handleRef = useRef<DocumentHandle | null>(null);

  useEffect(() => {
    if (!type || !resourceId || !accessToken) {
      setHandle(null); setSnapshot(null); setOpenError(null);
      return;
    }
    let cancelled = false;
    setOpenError(null);
    void Promise.resolve(openJsonDocument(type, resourceId, { token: accessToken, bookId }))
      .then((h) => {
        if (cancelled) { h.release(); return; }
        handleRef.current = h;
        setHandle(h);
        setSnapshot(h.getSnapshot());
      })
      .catch((e: unknown) => {
        if (!cancelled) setOpenError(e instanceof Error ? e.message : 'open failed');
      });
    return () => {
      cancelled = true;
      handleRef.current?.release();
      handleRef.current = null;
      setHandle(null);
      setSnapshot(null);
    };
  }, [type, resourceId, accessToken, bookId]);

  // Subscribe AFTER the handle lands; snapshot is cached-per-emit so setState dedupes by identity.
  useEffect(() => {
    if (!handle) return;
    setSnapshot(handle.getSnapshot());
    return handle.subscribe(() => setSnapshot(handle.getSnapshot()));
  }, [handle]);

  return { handle, snapshot, openError };
}
