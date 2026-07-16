// 34 arc-templates — the CONTROLLER (no JSX). Lifts the motif Arc* surface into a first-class S2
// panel: the library list (useArcLibrary, tier-merged), the active Work's projectId (materialize/
// apply need it; browse does not), and the CRUD the library was MISSING a UI for — create / adopt /
// archive (arcApi has them; nothing rendered them). Reuses the motif hooks/api in place (D-S2-ARC-SEAM
// — import, never edit S4's files).
import { useCallback, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { useArcLibrary } from '@/features/composition/motif/hooks/useArcLibrary';
import { currentUserId } from '@/features/composition/motif/currentUser';
import { arcApi } from '@/features/composition/motif/arcApi';
import type { ArcTemplate } from '@/features/composition/motif/arcTypes';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';

export type ArcTier = 'all' | 'mine' | 'system';

export interface ArcTemplatesState {
  token: string | null;
  projectId: string | null;
  templates: ArcTemplate[];
  loading: boolean;
  isError: boolean;
  refetch: () => void;
  tier: ArcTier;
  setTier: (t: ArcTier) => void;
  selected: ArcTemplate | null;
  select: (a: ArcTemplate | null) => void;
  meId: string | null;
  /** tier of a row, for the chip + whether Adopt/Archive apply. */
  tierOf: (a: ArcTemplate) => 'system' | 'mine' | 'public';
  busy: boolean;
  actionError: string | null;
  create: (args: { code: string; name: string; language?: string }) => Promise<void>;
  adopt: (id: string) => Promise<void>;
  archive: (id: string) => Promise<void>;
}

export function useArcTemplates(bookId: string): ArcTemplatesState {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const qc = useQueryClient();
  const meId = currentUserId();

  const work = useWorkResolution(bookId, token);
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  const projectId = useMemo(
    () => resolveActiveWork(work.data, activeWorkId)?.project_id ?? null,
    [work.data, activeWorkId],
  );

  const lib = useArcLibrary(token);
  const [tier, setTier] = useState<ArcTier>('all');
  const [selected, setSelected] = useState<ArcTemplate | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const templates = useMemo(() => {
    const all = lib.data ?? [];
    if (tier === 'mine') return all.filter((a) => a.owner_user_id === meId);
    if (tier === 'system') return all.filter((a) => a.owner_user_id === null);
    return all;
  }, [lib.data, tier, meId]);

  const tierOf = useCallback(
    (a: ArcTemplate): 'system' | 'mine' | 'public' =>
      a.owner_user_id === null ? 'system' : a.owner_user_id === meId ? 'mine' : 'public',
    [meId],
  );

  const invalidate = useCallback(
    () => qc.invalidateQueries({ queryKey: ['composition', 'arc-templates'] }),
    [qc],
  );

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      if (!token) return;
      setBusy(true); setActionError(null);
      try {
        await fn();
        await invalidate();
      } catch (e) {
        setActionError(e instanceof Error ? e.message : 'Action failed');
      } finally {
        setBusy(false);
      }
    },
    [token, invalidate],
  );

  const create = useCallback(
    (args: { code: string; name: string; language?: string }) =>
      run(() => arcApi.create({ language: 'en', ...args }, token!)),
    [run, token],
  );
  const adopt = useCallback((id: string) => run(() => arcApi.adopt(id, undefined, token!)), [run, token]);
  const archive = useCallback((id: string) => run(async () => {
    await arcApi.archive(id, token!);
    setSelected((s) => (s?.id === id ? null : s)); // close the detail if we archived the open one
  }), [run, token]);

  return {
    token, projectId,
    templates, loading: lib.isLoading, isError: lib.isError, refetch: () => void lib.refetch(),
    tier, setTier,
    selected, select: setSelected,
    meId, tierOf,
    busy, actionError,
    create, adopt, archive,
  };
}
