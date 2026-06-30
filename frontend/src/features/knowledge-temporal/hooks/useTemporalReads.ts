// Base react-query hooks for the KAL temporal reads. Each follows the repo convention: query
// key prefixed with userId (cross-tenant cache isolation on a shared QueryClient logout→login),
// enabled only when the token + ids are present, and a modest staleTime. The surface components
// (canonical card / timeline / diff / retrieval) consume these; the slider drives `asOf`.
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { kalApi } from '../api';
import type {
  CanonicalSnapshot,
  FactsResponse,
  TimelineResponse,
  TimelineEntry,
  RetrieveResponse,
} from '../types';

/**
 * Normalize a timeline row to the FLAT shape the components read. The live KAL returns flat
 * fact-like rows, but the frozen contract (kal.v1.yaml) declares a NESTED `{kind, fact, at_ordinal}`.
 * Tolerate both so a spec-conformant deployment doesn't render `undefined` fields + colliding keys.
 */
function normalizeTimelineRow(row: unknown): TimelineEntry {
  const r = (row ?? {}) as Record<string, unknown>;
  const nested = (r.fact ?? null) as Record<string, unknown> | null;
  const base = nested ? { ...nested, ...r } : r; // nested fact fields, with row-level kind/at_ordinal kept
  return base as unknown as TimelineEntry;
}

export function useCanonical(bookId: string | null, entityId: string | null, asOf?: number) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const q = useQuery({
    queryKey: ['kal-canonical', userId, bookId, entityId, asOf ?? 'head'] as const,
    queryFn: () => kalApi.getCanonical(bookId!, entityId!, accessToken!, asOf),
    enabled: !!accessToken && !!bookId && !!entityId,
    staleTime: 10_000,
  });
  return {
    canonical: (q.data ?? null) as CanonicalSnapshot | null,
    isLoading: q.isLoading,
    error: (q.error as Error | null) ?? null,
  };
}

export function useFacts(
  bookId: string | null,
  entityId: string | null,
  opts?: { asOf?: number; attrs?: string },
) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const q = useQuery({
    queryKey: ['kal-facts', userId, bookId, entityId, opts?.asOf ?? 'head', opts?.attrs ?? ''] as const,
    queryFn: () => kalApi.getFacts(bookId!, entityId!, accessToken!, opts),
    enabled: !!accessToken && !!bookId && !!entityId,
    staleTime: 10_000,
  });
  return {
    facts: (q.data as FactsResponse | undefined)?.items ?? [],
    temporalCapability: (q.data as FactsResponse | undefined)?.temporal_capability,
    isLoading: q.isLoading,
    error: (q.error as Error | null) ?? null,
  };
}

export function useTimeline(
  bookId: string | null,
  entityId: string | null,
  opts?: { cursor?: string; limit?: number },
) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const q = useQuery({
    queryKey: ['kal-timeline', userId, bookId, entityId, opts?.cursor ?? '', opts?.limit ?? 50] as const,
    queryFn: () => kalApi.getTimeline(bookId!, entityId!, accessToken!, opts),
    enabled: !!accessToken && !!bookId && !!entityId,
    staleTime: 10_000,
  });
  const raw = (q.data as TimelineResponse | undefined)?.items ?? [];
  return {
    items: raw.map(normalizeTimelineRow),
    nextCursor: (q.data as TimelineResponse | undefined)?.next_cursor ?? null,
    isLoading: q.isLoading,
    error: (q.error as Error | null) ?? null,
  };
}

export function useRetrieve(
  bookId: string | null,
  body: { query: string; scope?: string; k?: number; as_of?: number } | null,
) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const q = useQuery({
    queryKey: ['kal-retrieve', userId, bookId, body?.query ?? '', body?.scope ?? '', body?.k ?? 0, body?.as_of ?? 'head'] as const,
    queryFn: () => kalApi.retrieve(bookId!, body!, accessToken!),
    enabled: !!accessToken && !!bookId && !!body && !!body.query,
    staleTime: 30_000,
  });
  return {
    items: (q.data as RetrieveResponse | undefined)?.items ?? [],
    temporalCapability: (q.data as RetrieveResponse | undefined)?.temporal_capability,
    isLoading: q.isLoading,
    error: (q.error as Error | null) ?? null,
  };
}
