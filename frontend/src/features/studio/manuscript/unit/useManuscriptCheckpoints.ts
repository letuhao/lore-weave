// #16 Phase 1, task 1.2 — Checkpoints, ported from the legacy chapter editor
// (`features/composition/hooks/useTurnCheckpoints.ts`) onto Studio's Tier-4 manuscript hoist.
//
// Legacy captured a checkpoint at THREE seams on `ChapterEditorPage` (onAccept / applyPolish /
// the popout-insert relay) — none of those exist in Studio. Studio's single AI-write chokepoint
// is `ManuscriptUnitProvider.applyProposedEdit` (#16 P1, landed today) — every propose_edit Apply
// (insert_at_cursor or replace_selection) goes through it via `editorBridge`'s optional
// `applyProposedEdit` hoist action. So this hook exposes its OWN `applyProposedEdit` wrapper: same
// signature as the hoist's, captures a checkpoint on a successful write, then delegates. The
// caller (EditorPanel) hands the WRAPPED function to `registerEditorTarget` instead of the raw
// `unit.applyProposedEdit` — a drop-in swap, not a new integration seam.
//
// The durable truth stays the server-side chapter_revision spine (book-service snapshots one on
// every draft PATCH) — this hook is a curated in-memory view of restore points layered on top,
// exactly like the legacy hook (server-is-SoT, see useTurnCheckpoints.ts's header comment).
//
// G7 dirty-guard (spec #09 / `bookEffects.ts`'s `bookDraftEffect`): `restore()` refuses to
// overwrite a dirty hoist. It returns `{ ok: false, reason: 'dirty' }` rather than silently
// no-op'ing or clobbering unsaved keystrokes — the UI section additionally disables Restore
// up-front so this is a defense-in-depth backstop, not the primary UX signal. Return-result
// (not throw) matches the sibling #16 1.3 `useRevisionHistory.restore()` convention landed the
// same session — both are reload-capable restore actions reviewed together.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import type { ManuscriptUnitApi } from './ManuscriptUnitProvider';

export interface ManuscriptCheckpoint {
  id: string;
  chapterId: string;
  /** The latest chapter_revision id BEFORE this AI edit landed = the restore point. null when
   * the chapter had no revisions yet (nothing to restore to — Restore stays disabled). */
  preRevisionId: string | null;
  at: number;
  snippet: string;
  /** Consecutive AI edits sharing the same pre-revision fold into one row (no save committed
   * between them → restoring any of them is the same rollback). */
  count: number;
  kind: 'insert' | 'replace';
}

export type CheckpointRestoreResult =
  | { ok: true }
  | { ok: false; reason: 'dirty' | 'no-restore-point' | 'not-found' | 'error'; message?: string };

const MAX_CHECKPOINTS = 20;

/** `unit` is the active `ManuscriptUnitApi` (or null when no chapter is mounted / the panel
 * renders outside the provider — same nullability contract as `useManuscriptUnit()`). */
export function useManuscriptCheckpoints(bookId: string, unit: ManuscriptUnitApi | null) {
  const { accessToken } = useAuth();
  const [checkpoints, setCheckpoints] = useState<ManuscriptCheckpoint[]>([]);
  const checkpointsRef = useRef<ManuscriptCheckpoint[]>(checkpoints);
  checkpointsRef.current = checkpoints;

  const chapterId = unit?.state.chapterId ?? null;
  const version = unit?.state.version;

  // #16 integration fix — `unit` (the whole ManuscriptUnitApi) is a NEW object on every hoist
  // state change (its `useMemo` recomputes per keystroke), so a useCallback depending on `unit`
  // directly would get a new reference every keystroke too. EditorPanel.tsx hands `applyProposedEdit`
  // to a registerEditorTarget useEffect specifically engineered (#16 P1 review) to stay stable
  // across keystrokes — read the LATEST unit via a ref instead, mirroring latestRevIdRef above.
  const unitRef = useRef(unit);
  unitRef.current = unit;

  // Held synchronously (a ref, not state) so `applyProposedEdit` can pin the pre-edit restore
  // point WITHOUT an async listRevisions round-trip on every AI edit — mirrors legacy's
  // `latestRevIdRef`, which existed specifically to dodge a TOCTOU race against a concurrent
  // manual save landing between the read and the capture.
  const latestRevIdRef = useRef<string | null>(null);

  const refreshLatestRevision = useCallback(async (cid: string) => {
    if (!accessToken) { latestRevIdRef.current = null; return; }
    try {
      const r = await booksApi.listRevisions(accessToken, bookId, cid, { limit: 1, offset: 0 });
      latestRevIdRef.current = r.items[0]?.revision_id ?? null;
    } catch {
      // No revisions yet / offline → null restore point (Restore disabled), never throw.
      latestRevIdRef.current = null;
    }
  }, [accessToken, bookId]);

  // Refresh on chapter open AND on every draft_version bump, combined into ONE effect (not two
  // separate chapterId/version watchers — a chapter switch changes both together, so a combined
  // key avoids firing twice for the same event). /review-impl cross-hook finding: the sibling
  // #16 1.3 `useRevisionHistory` restore path (a DIFFERENT hook instance, same chapter) also
  // mutates the server-side chapter_revision spine via reload(), which bumps `state.version` —
  // watching only the 'saved' TRANSITION missed that path entirely, so a Revision-History-
  // triggered restore left `latestRevIdRef` stale: the NEXT AI-edit checkpoint would then capture
  // the WRONG restore point (reverting further back than "just before this edit" on its own
  // Restore). `version` changes on every save AND every reload (openUnit/reload/restore all
  // re-fetch via getDraft), so watching it here covers both hooks' restore paths with one
  // mechanism — this hook's own `restore()` relies on it too, so it doesn't separately call
  // `refreshLatestRevision` itself (would otherwise double-fetch on top of this effect).
  const prevKeyRef = useRef<string | null>(null);
  useEffect(() => {
    const key = chapterId ? `${chapterId}:${version ?? ''}` : null;
    if (key === prevKeyRef.current) return;
    prevKeyRef.current = key;
    if (chapterId) void refreshLatestRevision(chapterId);
    else latestRevIdRef.current = null;
  }, [chapterId, version, refreshLatestRevision]);

  const capture = useCallback((cid: string, snippet: string, kind: 'insert' | 'replace') => {
    setCheckpoints((prev) => {
      const pre = latestRevIdRef.current;
      const last = prev[0];
      if (last && last.chapterId === cid && last.preRevisionId === pre) {
        // Fold: keep the FIRST edit's snippet (Restore rolls back to before it) — overwriting
        // with the newest snippet would mislabel the row against what Restore actually reverts.
        const folded: ManuscriptCheckpoint = { ...last, count: last.count + 1, at: Date.now() };
        return [folded, ...prev.slice(1)];
      }
      const cp: ManuscriptCheckpoint = {
        id: `${cid}:${Date.now()}:${Math.random().toString(36).slice(2, 6)}`,
        chapterId: cid, preRevisionId: pre, at: Date.now(), snippet: snippet.slice(0, 80), count: 1, kind,
      };
      return [cp, ...prev].slice(0, MAX_CHECKPOINTS);
    });
  }, []);

  // The wrapped write seam. Same signature as `ManuscriptUnitApi['applyProposedEdit']` — a
  // drop-in replacement at the ONE call site that feeds `registerEditorTarget` (EditorPanel).
  // Captures the pre-edit snapshot BEFORE delegating so a folded/failed apply never mutates the
  // checkpoint list for nothing.
  const applyProposedEdit = useCallback(
    (params: Parameters<ManuscriptUnitApi['applyProposedEdit']>[0]) => {
      const u = unitRef.current;
      if (!u) return false;
      const cid = u.state.chapterId;
      const ok = u.applyProposedEdit(params);
      if (ok && cid) {
        capture(cid, params.text, params.operation === 'replace_selection' ? 'replace' : 'insert');
      }
      return ok;
    },
    [capture],
  );

  const restore = useCallback(async (checkpointId: string): Promise<CheckpointRestoreResult> => {
    const cp = checkpointsRef.current.find((c) => c.id === checkpointId);
    if (!cp) return { ok: false, reason: 'not-found' };
    if (!accessToken || !cp.preRevisionId) {
      return { ok: false, reason: 'no-restore-point', message: 'No earlier version to restore to.' };
    }
    // G7 — never clobber a dirty hoist with a restore. The UI section disables Restore up-front;
    // this is the backstop for a race (dirtied between render and click) or a non-UI caller.
    if (unit?.isChapterDirty(cp.chapterId)) {
      return {
        ok: false, reason: 'dirty',
        message: 'Save or discard your current edits before restoring a checkpoint.',
      };
    }
    try {
      await booksApi.restoreRevision(accessToken, bookId, cp.chapterId, cp.preRevisionId);
    } catch (e) {
      return { ok: false, reason: 'error', message: (e as Error).message };
    }
    // This checkpoint (and any NEWER same-chapter ones) are now moot — the draft is back at
    // cp.preRevisionId. Newest-first array ⇒ "newer" = a LOWER index than cp.
    setCheckpoints((prev) => {
      const idx = prev.findIndex((c) => c.id === cp.id);
      if (idx < 0) return prev;
      return prev.filter((c, i) => c.id !== cp.id && !(c.chapterId === cp.chapterId && i < idx));
    });
    // Reload the hoist so the editor reflects the restored body (only if it's still the active
    // unit — the user may have navigated away while the restore call was in flight). The reload's
    // version bump is picked up by the chapterId+version effect above (not an explicit
    // refreshLatestRevision call here) — if the user navigated away, that chapter's checkpoints
    // were already dropped above, and reopening it later re-triggers the effect via chapterId.
    if (unit && unit.state.chapterId === cp.chapterId) {
      await unit.reload();
    }
    return { ok: true };
  }, [accessToken, bookId, unit]);

  const visibleCheckpoints = chapterId
    ? checkpoints.filter((c) => c.chapterId === chapterId)
    : [];

  return { checkpoints, visibleCheckpoints, capture, applyProposedEdit, restore };
}
