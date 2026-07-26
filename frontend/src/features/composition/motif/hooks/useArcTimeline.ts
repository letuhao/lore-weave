// W10 arc-timeline — the EDIT CONTROLLER. Owns: fetch one arc-template, hold a local
// working copy of its placements, apply the frozen ArcTimelineEdit actions through the
// pure `applyArcEdit` reducer (optimistic), and persist the layout back with a debounced
// If-Match PATCH. No JSX. The single useEffect is SYNCHRONIZATION (seed the working copy
// from freshly-fetched server data), never event-handling — edits flow through onEdit.
//
// Edit-gating: only the OWNER of an active arc may edit (a system/foreign row PATCHes
// to a 404 — the "clone to edit" affordance). `onEdit` is undefined for a read-only
// arc, which the contract renders non-interactive.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { arcApi } from '../arcApi';
import type { ArcTemplate } from '../arcTypes';
import type { ArcPlacement, ArcThread, ArcTimelineEdit } from '../arcTimelineContract';
import {
  applyArcEdit, layoutToPlacements, placementsToLayout, threadsToContract,
} from '../applyArcEdit';
import { currentUserId } from '../currentUser';

const PERSIST_DEBOUNCE_MS = 600;

export type UseArcTimelineResult = {
  arc: ArcTemplate | undefined;
  isLoading: boolean;
  isError: boolean;
  threads: ArcThread[];
  placements: ArcPlacement[];
  chapterSpan: number;
  canEdit: boolean;
  /** Apply a frozen edit (optimistic) + schedule the debounced persist. */
  onEdit: (edit: ArcTimelineEdit) => void;
  /** PATCH state for the editor's save indicator. */
  saving: boolean;
  saveError: 'conflict' | 'error' | null;
};

export function useArcTimeline(arcId: string | null, token: string | null): UseArcTimelineResult {
  const qc = useQueryClient();
  const query = useQuery<ArcTemplate>({
    queryKey: ['composition', 'arc-template', arcId],
    queryFn: () => arcApi.get(arcId!, token!),
    enabled: !!arcId && !!token,
    staleTime: 30_000,
  });
  const arc = query.data;

  // local working copy of placements (the edit surface mutates this, not the cache).
  const [placements, setPlacements] = useState<ArcPlacement[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<'conflict' | 'error' | null>(null);

  // version we last seeded from / are persisting against (optimistic concurrency).
  const versionRef = useRef<number>(0);
  const seededVersionRef = useRef<number>(-1);
  const placementsRef = useRef<ArcPlacement[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const chapterSpan = Math.max(1, arc?.chapter_span ?? 1);
  const threads = useMemo(() => threadsToContract(arc?.threads ?? []), [arc?.threads]);

  const canEdit =
    !!arc && arc.owner_user_id !== null && arc.owner_user_id === currentUserId() && arc.status === 'active';

  // SYNCHRONIZATION: when the server delivers a NEWER version than we last seeded
  // (initial load, or a successful PATCH bumped it), reset the working copy to it.
  // Local edits between server versions are preserved (we don't re-seed on identity).
  useEffect(() => {
    if (!arc) return;
    if (arc.version !== seededVersionRef.current) {
      const seeded = layoutToPlacements(arc.layout);
      setPlacements(seeded);
      placementsRef.current = seeded;
      versionRef.current = arc.version;
      seededVersionRef.current = arc.version;
    }
  }, [arc]);

  const persist = useCallback(async () => {
    if (!arcId || !token) return;
    setSaving(true);
    setSaveError(null);
    const layout = placementsToLayout(placementsRef.current);
    try {
      const updated = await arcApi.patch(arcId, { layout }, versionRef.current, token);
      // adopt the server's new version as the next If-Match; re-seed baseline silently.
      versionRef.current = updated.version;
      seededVersionRef.current = updated.version;
      qc.setQueryData(['composition', 'arc-template', arcId], updated);
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 412) {
        setSaveError('conflict');
        // a concurrent edit won — refetch the authoritative row to reconcile.
        qc.invalidateQueries({ queryKey: ['composition', 'arc-template', arcId] });
      } else {
        setSaveError('error');
      }
    } finally {
      setSaving(false);
    }
  }, [arcId, token, qc]);

  const schedulePersist = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    // NULL the ref as the timer fires, so the unmount-flush below only re-fires a
    // GENUINELY-pending edit — never a duplicate of one already in flight.
    timerRef.current = setTimeout(() => { timerRef.current = null; void persist(); }, PERSIST_DEBOUNCE_MS);
  }, [persist]);

  const onEdit = useCallback(
    (edit: ArcTimelineEdit) => {
      setPlacements((prev) => {
        const next = applyArcEdit(prev, edit, chapterSpan);
        placementsRef.current = next;
        return next;
      });
      schedulePersist();
    },
    [chapterSpan, schedulePersist],
  );

  // flush a pending debounce on unmount so a last edit isn't lost.
  useEffect(() => () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      void persist();
    }
  }, [persist]);

  return {
    arc,
    isLoading: query.isLoading,
    isError: query.isError,
    threads,
    placements,
    chapterSpan,
    canEdit,
    onEdit,
    saving,
    saveError,
  };
}
