import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { tieringApi } from '../tieringApi';
import { glossaryApi } from '../api';
import type { Tier } from '../tieringTypes';

/** A pickable standard (genre or kind) for the adopt pick-list — identified by code. */
export interface StandardPick {
  code: string;
  name: string;
  icon: string;
  tier: Tier; // 'system' | 'user'
}

/** Dedup by code, preferring the User tier (it shadows System at adopt by code). */
function mergeByCode(system: StandardPick[], user: StandardPick[]): StandardPick[] {
  const byCode = new Map<string, StandardPick>();
  for (const s of system) byCode.set(s.code, s);
  for (const u of user) byCode.set(u.code, u); // user shadows system
  return [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * The standards a book can ADOPT (R1 pick-list source): merged System + caller's User
 * genres and kinds, keyed by code (User shadows System — the same resolution the
 * backend applies at adopt). Read-only; the adopt itself lives in useBookOntology.
 */
export function useStandards() {
  const { accessToken } = useAuth();
  const enabled = !!accessToken;

  const genresQ = useQuery({
    queryKey: ['glossary-std-genres'],
    queryFn: () => tieringApi.listGenres(accessToken!),
    enabled,
  });
  const sysKindsQ = useQuery({
    queryKey: ['glossary-std-system-kinds'],
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled,
  });
  const userKindsQ = useQuery({
    queryKey: ['glossary-std-user-kinds'],
    queryFn: () => tieringApi.listUserKinds(accessToken!),
    enabled,
  });

  const genres: StandardPick[] = (genresQ.data ?? []).map((g) => ({
    code: g.code,
    name: g.name,
    icon: g.icon,
    tier: g.tier,
  }));

  const kinds: StandardPick[] = mergeByCode(
    (sysKindsQ.data ?? []).map((k) => ({
      code: k.code,
      name: k.name,
      icon: (k as { icon?: string }).icon ?? '',
      tier: 'system' as const,
    })),
    (userKindsQ.data ?? []).map((k) => ({
      code: k.code,
      name: k.name,
      icon: k.icon,
      tier: 'user' as const,
    })),
  );

  return {
    genres,
    kinds,
    isLoading: genresQ.isLoading || sysKindsQ.isLoading || userKindsQ.isLoading,
    error: genresQ.error || sysKindsQ.error || userKindsQ.error,
  };
}
