import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '@/features/glossary/tieringApi';
import { glossaryApi } from '@/features/glossary/api';
import type { Genre } from '@/features/glossary/tieringTypes';

/**
 * A merged standards row (genre OR kind) for the per-user Standards Library. The
 * System and User tiers are merged by `code` — the User row SHADOWS the System one
 * (the same resolution the backend applies at adopt) — so a code the user cloned
 * shows as a single USER row (editable), and codes they haven't cloned show as
 * read-only SYS rows (clone-only). `cloneFromId` is the SYSTEM row's id, carried so
 * a SYS row can clone-by-id; `id` is the row's own id (user_*_id for USER rows).
 */
export interface KindRow {
  id: string; // user_kind_id (user) | kind_id (system)
  code: string;
  name: string;
  description: string | null;
  icon: string;
  color: string;
  tier: 'system' | 'user';
  clonedFromKindId?: string | null;
}

// Shared query keys with useStandards so a clone refreshes BOTH the library and the
// adopt pick-list (the standards feed the book adopt flow).
const QK_GENRES = ['glossary-std-genres'];
const QK_SYS_KINDS = ['glossary-std-system-kinds'];
const QK_USER_KINDS = ['glossary-std-user-kinds'];

/** User shadows System by code; stable sort by code. */
function shadowByCode<T extends { code: string; tier: string }>(rows: T[]): T[] {
  const byCode = new Map<string, T>();
  for (const r of rows) {
    const cur = byCode.get(r.code);
    if (!cur || (cur.tier === 'system' && r.tier === 'user')) byCode.set(r.code, r);
  }
  return [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * Controller for the Standards Library (`/standards`). Reads the merged System+User
 * genres & kinds and exposes clone-from-System mutations (M1). Edit/delete + trash
 * land in later milestones. Everything is owner-scoped server-side (G2 tenancy).
 */
export function useUserStandards() {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const enabled = !!accessToken;

  const genresQ = useQuery({
    queryKey: QK_GENRES,
    queryFn: () => tieringApi.listGenres(accessToken!),
    enabled,
  });
  const sysKindsQ = useQuery({
    queryKey: QK_SYS_KINDS,
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled,
  });
  const userKindsQ = useQuery({
    queryKey: QK_USER_KINDS,
    queryFn: () => tieringApi.listUserKinds(accessToken!),
    enabled,
  });

  // Genres come from /genres already tier-tagged (System + User, un-shadowed) →
  // shadow client-side so a cloned code collapses to its single USER row.
  const genres: Genre[] = useMemo(
    () => shadowByCode((genresQ.data ?? []).filter((g) => g.tier !== 'book')),
    [genresQ.data],
  );

  const kinds: KindRow[] = useMemo(() => {
    const sys: KindRow[] = (sysKindsQ.data ?? []).map((k) => ({
      id: k.kind_id,
      code: k.code,
      name: k.name,
      description: k.description ?? null,
      icon: k.icon,
      color: k.color,
      tier: 'system' as const,
    }));
    const user: KindRow[] = (userKindsQ.data ?? []).map((k) => ({
      id: k.user_kind_id,
      code: k.code,
      name: k.name,
      description: k.description ?? null,
      icon: k.icon,
      color: k.color,
      tier: 'user' as const,
      clonedFromKindId: k.cloned_from_kind_id ?? null,
    }));
    return shadowByCode([...sys, ...user]);
  }, [sysKindsQ.data, userKindsQ.data]);

  const invalidateGenres = () => qc.invalidateQueries({ queryKey: QK_GENRES });
  const invalidateKinds = () => {
    qc.invalidateQueries({ queryKey: QK_SYS_KINDS });
    qc.invalidateQueries({ queryKey: QK_USER_KINDS });
  };

  // Clone a System genre into the caller's User tier (same code, FK-guarded → 422).
  const cloneGenre = useMutation({
    mutationFn: (g: Genre) =>
      tieringApi.createUserGenre(
        {
          code: g.code,
          name: g.name,
          icon: g.icon,
          color: g.color,
          sort_order: g.sort_order,
          clone_from_genre_id: g.genre_id,
        },
        accessToken!,
      ),
    onSuccess: invalidateGenres,
  });

  const cloneKind = useMutation({
    mutationFn: (k: KindRow) =>
      tieringApi.createUserKind(
        {
          code: k.code,
          name: k.name,
          description: k.description,
          icon: k.icon,
          color: k.color,
          clone_from_kind_id: k.id,
        },
        accessToken!,
      ),
    onSuccess: invalidateKinds,
  });

  return {
    genres,
    kinds,
    isLoading: genresQ.isLoading || sysKindsQ.isLoading || userKindsQ.isLoading,
    error: genresQ.error || sysKindsQ.error || userKindsQ.error,
    cloneGenre,
    cloneKind,
    invalidateGenres,
    invalidateKinds,
  };
}
