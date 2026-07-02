// #12 S2 — the stock DocumentHandle for simple load/save providers (one resource, one etag).
// Providers with composite documents or an existing owner store (the manuscript hoist, R2)
// implement DocumentHandle themselves; everything else should use this.
import type { DocumentHandle, DocumentSnapshot, DocumentStatus } from './types';

export interface FetchHandleIO {
  load(): Promise<{ doc: unknown; etag: string | number }>;
  /** Persist; throw {conflict:true} (or an Error) to surface conflict/error on the snapshot. */
  save(doc: unknown, etag: string | number | null): Promise<{ etag: string | number }>;
}

export function createFetchDocumentHandle(
  type: string,
  resourceId: string,
  io: FetchHandleIO,
): DocumentHandle {
  let base: unknown = null;         // last loaded/saved doc (revert target)
  let working: unknown = null;      // current edits (null = untouched)
  let etag: string | number | null = null;
  let status: DocumentStatus = 'loading';
  let detail: string | null = null;
  let snapshot: DocumentSnapshot | null = null; // cached — getSnapshot must be referentially stable
  const listeners = new Set<() => void>();

  const emit = () => {
    snapshot = null;
    listeners.forEach((l) => l());
  };

  const build = (): DocumentSnapshot => ({
    doc: working ?? base,
    etag,
    dirty: working != null && JSON.stringify(working) !== JSON.stringify(base),
    status,
    detail,
  });

  const doLoad = async () => {
    status = 'loading';
    detail = null;
    emit();
    try {
      const r = await io.load();
      base = r.doc;
      etag = r.etag;
      // G7/R6: a reload must never clobber local edits — keep `working` as-is.
      status = 'idle';
    } catch (e) {
      status = 'error';
      detail = e instanceof Error ? e.message : 'load failed';
    }
    emit();
  };

  const initial = doLoad();

  return {
    type,
    resourceId,
    getSnapshot: () => (snapshot ??= build()),
    subscribe: (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    update: (doc) => {
      working = doc;
      if (status === 'conflict' || status === 'error') { status = 'idle'; detail = null; }
      emit();
    },
    save: async () => {
      await initial.catch(() => {});
      if (working == null) return; // nothing to save
      status = 'saving';
      detail = null;
      emit();
      try {
        const r = await io.save(working, etag);
        base = working;
        working = null;
        etag = r.etag;
        status = 'idle';
      } catch (e) {
        const conflict = !!(e && typeof e === 'object' && (e as { conflict?: unknown }).conflict);
        status = conflict ? 'conflict' : 'error';
        detail = e instanceof Error ? e.message : conflict ? 'conflict' : 'save failed';
      }
      emit();
    },
    revert: () => {
      working = null;
      status = 'idle';
      detail = null;
      emit();
    },
    reload: () => doLoad(),
    release: () => {
      listeners.clear();
    },
  };
}
