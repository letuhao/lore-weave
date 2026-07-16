// W6 §3.2 — the library list controller (react-query). Owns: the list query, the
// scope tab (my | catalog), client-side facet narrowing over the fetched page
// (the server does the heavy filter), and a debounced search. No JSX.
//
// Two distinct query paths (D-MOTIF-FE-CATALOG-ENDPOINT):
//   • 'my'      → GET /motifs scope='all'  → full Motif rows (owner/author view).
//   • 'catalog' → GET /motifs/catalog      → the B-3 allow-list (CatalogMotif —
//                 NO owner_user_id / visibility / examples / source_ref). The
//                 catalog tab is all-public by definition, so we normalize each
//                 CatalogMotif into a Motif-shaped, public-tier row for the card
//                 (the tier facet is N/A on this tab — every row is 'public').
import { useMemo, useState } from 'react';
import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { motifApi, type MotifListParams, type CatalogParams } from '../api';
import type { CatalogMotif, Motif, MotifKind } from '../types';

// The six library tiers (§3.1). `my` = your globals + system; `book`/`shared` come from
// ONE GET /motifs/book/{id} response, partitioned client-side (book_id vs book_shared);
// `system` = the seeded defaults; `catalog` = the public allow-list; `drafts` = your mined
// review queue. `book`/`shared` need a bookId (disabled without one).
export type LibraryScope = 'my' | 'book' | 'shared' | 'system' | 'catalog' | 'drafts';

export type MotifFacets = {
  kind?: MotifKind;
  genre?: string;
  tension?: number;     // exact T1..T5 narrowing
  tier?: 'system' | 'user' | 'public';
};

// A catalog row carries a sentinel non-null owner_user_id so motifTier() resolves
// it to 'public' (it never equals the viewer). The allow-list omits the authored
// fields (examples/roles/beats/preconditions/effects), so we fill display-safe
// defaults — the card only reads name/kind/tension/summary/source/status here; the
// full detail is fetched on Open via motifApi.get (which redacts server-side).
const CATALOG_OWNER_SENTINEL = '__catalog__';

function catalogToMotif(c: CatalogMotif): Motif {
  return {
    id: c.id,
    owner_user_id: CATALOG_OWNER_SENTINEL,   // non-null + ≠ viewer ⇒ tier 'public'
    code: c.code,
    language: c.language,
    visibility: 'public',
    kind: c.kind,
    category: c.category,
    name: c.name,
    summary: c.summary,
    genre_tags: c.genre_tags,
    roles: [],
    beats: [],
    preconditions: [],
    effects: [],
    tension_target: c.tension_target,
    emotion_target: c.emotion_target,
    info_asymmetry: null,
    examples: [],                            // allow-list never ships authored prose
    abstraction_confidence: c.abstraction_confidence,
    source: c.source,
    source_version: null,
    judge_score: c.judge_score,
    mining_support: null,
    status: 'active',                        // list_public is active-only
    version: c.version,
  };
}

export function useMotifLibrary(
  token: string | null,
  opts?: { initialScope?: LibraryScope; bookId?: string | null },
) {
  const bookId = opts?.bookId ?? null;
  const [scope, setScope] = useState<LibraryScope>(opts?.initialScope ?? 'my');
  const [search, setSearch] = useState('');
  const [facets, setFacets] = useState<MotifFacets>({});

  const q = search.trim() || undefined;

  // §2#9 scale — the /motifs route caps limit at 100 (le=100), so a >100 library paginates by
  // OFFSET via useInfiniteQuery ("Load more"). The FLAT-LIST scopes (my/system/drafts/catalog)
  // support offset; book/shared use the merged book endpoint (single page, partitioned client-side
  // — a book rarely exceeds one page). ONE infinite query, dispatched by scope.
  const PAGE = 100;
  const flatScope = scope === 'my' || scope === 'system' || scope === 'drafts' || scope === 'catalog';

  const fetchPage = async (offset: number): Promise<Motif[]> => {
    if (scope === 'system') return (await motifApi.list({ scope: 'system', q, limit: PAGE, offset }, token!)).motifs;
    if (scope === 'drafts') return (await motifApi.list({ scope: 'mine', status: 'draft', q, limit: PAGE, offset }, token!)).motifs;
    if (scope === 'catalog') return (await motifApi.catalog({ q, limit: PAGE, offset }, token!)).items.map(catalogToMotif);
    return (await motifApi.list({ scope: 'all', q, limit: PAGE, offset }, token!)).motifs;   // 'my'
  };
  const listQuery = useInfiniteQuery({
    queryKey: ['composition', 'motifs', 'list', scope, q],
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: 0,
    // a full page ⇒ there may be more; the next offset is pages*PAGE. A short page ⇒ done.
    getNextPageParam: (lastPage, allPages) => (lastPage.length === PAGE ? allPages.length * PAGE : undefined),
    enabled: !!token && flatScope,
  });

  // 'book' + 'shared' tabs: ONE GET /motifs/book/{id} response feeds BOTH (§3.1) — it merges the
  // caller's globals + this book's private labels + its book_shared rows; we partition it below.
  const bookQuery = useQuery({
    queryKey: ['composition', 'motifs', 'book', bookId, q],
    queryFn: () => motifApi.book(bookId!, token!, { q }),
    enabled: !!token && !!bookId && (scope === 'book' || scope === 'shared'),
    select: (d): Motif[] => d.motifs,
  });

  const flatRows = useMemo<Motif[]>(() => (listQuery.data?.pages ?? []).flat(), [listQuery.data]);

  // Partition the merged book response (Book = this book's private labels; Shared = book_shared —
  // §3.1, the book_id test is load-bearing); flat scopes use the accumulated infinite pages.
  const baseData = useMemo<Motif[]>(() => {
    if (scope === 'book') return (bookQuery.data ?? []).filter((m) => m.book_id === bookId && !m.book_shared);
    if (scope === 'shared') return (bookQuery.data ?? []).filter((m) => m.book_shared === true);
    return flatRows;
  }, [scope, bookId, bookQuery.data, flatRows]);

  // The active query handle for loading/error/refetch (the scope decides which one is live).
  const active = flatScope ? listQuery : bookQuery;

  // Client-side facet narrowing over the accumulated rows (cheap; the server did scope/q). Derived.
  const motifs = useMemo<Motif[]>(() => baseData.filter((m) => {
    if (facets.kind && m.kind !== facets.kind) return false;
    if (facets.genre && !m.genre_tags.includes(facets.genre)) return false;
    if (facets.tension != null && m.tension_target !== facets.tension) return false;
    if (facets.tier) {
      const tier = m.owner_user_id == null ? 'system' : (m.visibility === 'public' ? 'public' : 'user');
      if (tier !== facets.tier) return false;
    }
    return true;
  }), [baseData, facets]);

  const setFacet = <K extends keyof MotifFacets>(k: K, v: MotifFacets[K]) =>
    setFacets((prev) => ({ ...prev, [k]: prev[k] === v ? undefined : v }));
  const clearFacets = () => setFacets({});

  const available = useMemo(() => {
    const genres = new Set<string>();
    const kinds = new Set<MotifKind>();
    for (const m of baseData) {
      m.genre_tags.forEach((g) => genres.add(g));
      kinds.add(m.kind);
    }
    return { genres: [...genres].sort(), kinds: [...kinds].sort() };
  }, [baseData]);

  const isEmpty = !active.isLoading && !active.isError && motifs.length === 0 && baseData.length === 0;
  const hasMore = flatScope ? (listQuery.hasNextPage ?? false) : false;
  // book/shared aren't offset-paginated (the merged book route caps at 100) — so a >100-motif book
  // still needs the no-silent-cap SIGNAL (the flat scopes get real load-more instead).
  const truncated = !flatScope && (bookQuery.data?.length ?? 0) >= 100;

  return {
    motifs,
    isLoading: active.isLoading,
    isError: active.isError,
    error: active.error,
    refetch: active.refetch,
    isEmpty,
    scope, setScope,
    search, setSearch,
    facets, setFacet, clearFacets,
    available,
    rawCount: baseData.length,
    hasBook: !!bookId,
    // §2#9 scale — real pagination: "Load more" fetches the next offset page (flat scopes only);
    // book/shared (not offset-paginated) fall back to a no-silent-cap truncation signal.
    hasMore,
    isLoadingMore: flatScope ? listQuery.isFetchingNextPage : false,
    loadMore: () => { if (hasMore && !listQuery.isFetchingNextPage) void listQuery.fetchNextPage(); },
    truncated,
  };
}
