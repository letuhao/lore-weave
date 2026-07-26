// 34 arc-templates — the CONTROLLER (no JSX). Lifts the motif Arc* surface into a first-class S2
// panel: the library list (useArcLibrary, tier-merged), the active Work's projectId (materialize/
// apply need it; browse does not), and the CRUD the library was MISSING a UI for — create / adopt /
// archive (arcApi has them; nothing rendered them). Reuses the motif hooks/api in place (D-S2-ARC-SEAM
// — import, never edit S4's files).
import { useCallback, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { useArcLibrary } from '@/features/composition/motif/hooks/useArcLibrary';
import { currentUserId } from '@/features/composition/motif/currentUser';
import { arcApi } from '@/features/composition/motif/arcApi';
import type { ArcTemplate } from '@/features/composition/motif/arcTypes';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { listBookSharedTemplates, createSharedTemplate } from '@/features/composition/arcTemplates/api';

export type ArcTier = 'all' | 'mine' | 'system' | 'book' | 'archived';

/** Scale guard (§2.9): the library is fetched whole, so cap what we RENDER and say so — a huge
 *  library never silently truncates or janks the panel. Browse the long tail via the Catalog tab. */
export const ARC_TEMPLATE_RENDER_CAP = 200;

export interface ArcTemplatesState {
  token: string | null;
  projectId: string | null;
  bookId: string;
  templates: ArcTemplate[];
  /** true when the tier holds more than the render cap — the panel shows an honest "first N" notice. */
  truncated: boolean;
  totalInTier: number;
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
  create: (args: { code: string; name: string; language?: string; shareToBook?: boolean }) => Promise<void>;
  adopt: (id: string) => Promise<void>;
  archive: (id: string) => Promise<void>;
  restore: (id: string) => Promise<void>;
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

  // 34a — the book's SHARED tier is a SEPARATE (VIEW-gated) fetch, not a filter over the user lib.
  const bookLib = useQuery({
    queryKey: ['composition', 'arc-templates', 'book', bookId],
    queryFn: () => listBookSharedTemplates(bookId, token!),
    enabled: !!token && !!bookId && tier === 'book',
  });

  // S-08 — archived rows are a SEPARATE fetch (the default library list is active-only). This is
  // what makes Restore reachable: without an archived view a soft-deleted arc is invisible → a dead
  // end. Owner-scoped (you only archive/restore your own).
  const archivedLib = useQuery({
    queryKey: ['composition', 'arc-templates', 'archived'],
    queryFn: async () => (await arcApi.list({ scope: 'mine', status: 'archived', limit: 100 }, token!)).arc_templates,
    enabled: !!token && tier === 'archived',
  });

  const allInTier = useMemo(() => {
    if (tier === 'book') return bookLib.data ?? [];
    if (tier === 'archived') return archivedLib.data ?? [];
    const all = lib.data ?? [];
    if (tier === 'mine') return all.filter((a) => a.owner_user_id === meId);
    if (tier === 'system') return all.filter((a) => a.owner_user_id === null);
    return all;
  }, [tier, bookLib.data, archivedLib.data, lib.data, meId]);
  // Scale (§2.9): the library is fetched whole; cap what we RENDER + surface the cap honestly
  // (the Catalog tab is the paged path for browsing beyond this) — never a silent truncation.
  const templates = useMemo(() => allInTier.slice(0, ARC_TEMPLATE_RENDER_CAP), [allInTier]);
  const truncated = allInTier.length > ARC_TEMPLATE_RENDER_CAP;
  const totalInTier = allInTier.length;

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
    (args: { code: string; name: string; language?: string; shareToBook?: boolean }) =>
      run(() => args.shareToBook && bookId
        ? createSharedTemplate({ code: args.code, name: args.name, language: args.language }, bookId, token!)
        : arcApi.create({ language: 'en', code: args.code, name: args.name }, token!)),
    [run, token, bookId],
  );
  const adopt = useCallback((id: string) => run(() => arcApi.adopt(id, undefined, token!)), [run, token]);
  const archive = useCallback((id: string) => run(async () => {
    await arcApi.archive(id, token!);
    setSelected((s) => (s?.id === id ? null : s)); // close the detail if we archived the open one
  }), [run, token]);
  // S-08 — un-archive back into the active library. `run` invalidates the whole arc-templates key,
  // so both the archived list AND the active tiers refresh (the row moves out of Archived, into Mine).
  const restore = useCallback((id: string) => run(async () => {
    await arcApi.restore(id, token!);
    setSelected((s) => (s?.id === id ? null : s));
  }), [run, token]);

  const active = tier === 'book' ? bookLib : tier === 'archived' ? archivedLib : lib;
  return {
    token, projectId, bookId,
    templates, truncated, totalInTier, loading: active.isLoading, isError: active.isError,
    refetch: () => void active.refetch(),
    tier, setTier,
    selected, select: setSelected,
    meId, tierOf,
    busy, actionError,
    create, adopt, archive, restore,
  };
}
