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
import { useQuery } from '@tanstack/react-query';
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

  // 'my' tab: GET /motifs scope='all' (owned + system; NOT others' public).
  // limit 100 = the router's le=100 cap (sending more 422s — R-NODE-P1).
  const myParams: MotifListParams = { scope: 'all', q, limit: 100 };
  const myQuery = useQuery({
    queryKey: ['composition', 'motifs', 'my', q],
    queryFn: () => motifApi.list(myParams, token!),
    enabled: !!token && scope === 'my',
    select: (d): Motif[] => d.motifs,
  });

  // 'system' tab: GET /motifs scope='system' (the seeded defaults only — read-only tier).
  const systemQuery = useQuery({
    queryKey: ['composition', 'motifs', 'system', q],
    queryFn: () => motifApi.list({ scope: 'system', q, limit: 100 }, token!),
    enabled: !!token && scope === 'system',
    select: (d): Motif[] => d.motifs,
  });

  // 'book' + 'shared' tabs: ONE GET /motifs/book/{id} response feeds BOTH (§3.1) — it
  // merges the caller's globals + this book's private labels + its book_shared rows, each
  // carrying book_id + book_shared. We partition it below; do NOT fetch it twice. Needs a
  // book (disabled otherwise, so the tabs read empty rather than 422).
  const bookQuery = useQuery({
    queryKey: ['composition', 'motifs', 'book', bookId, q],
    queryFn: () => motifApi.book(bookId!, token!, { q }),
    enabled: !!token && !!bookId && (scope === 'book' || scope === 'shared'),
    select: (d): Motif[] => d.motifs,
  });

  // 'catalog' tab: GET /motifs/catalog (the B-3 allow-list). NO scope param; the
  // CatalogMotif rows are normalized to public-tier Motif rows for the shared card.
  const catalogParams: CatalogParams = { q, limit: 100 };
  const catalogQuery = useQuery({
    queryKey: ['composition', 'motifs', 'catalog', q],
    queryFn: () => motifApi.catalog(catalogParams, token!),
    enabled: !!token && scope === 'catalog',
    select: (d): Motif[] => d.items.map(catalogToMotif),
  });

  // 'drafts' tab (WI-1) — the mining review queue: YOUR draft motifs (status='draft',
  // source='mined'), which the default 'my' list (active-only) hides. Promote/discard
  // act on these.
  const draftsParams: MotifListParams = { scope: 'mine', status: 'draft', q, limit: 100 };
  const draftsQuery = useQuery({
    queryKey: ['composition', 'motifs', 'drafts', q],
    queryFn: () => motifApi.list(draftsParams, token!),
    enabled: !!token && scope === 'drafts',
    select: (d): Motif[] => d.motifs,
  });

  const query =
    scope === 'catalog' ? catalogQuery
    : scope === 'drafts' ? draftsQuery
    : scope === 'system' ? systemQuery
    : scope === 'book' || scope === 'shared' ? bookQuery
    : myQuery;

  // The book endpoint merges three tiers into one list; partition it by the row flags so
  // the Book tab shows only THIS book's private labels (never the globals already on Mine)
  // and Shared shows only the book_shared rows (§3.1 — the book_id test is load-bearing).
  const baseData = useMemo<Motif[]>(() => {
    if (scope === 'book') return (bookQuery.data ?? []).filter((m) => m.book_id === bookId && !m.book_shared);
    if (scope === 'shared') return (bookQuery.data ?? []).filter((m) => m.book_shared === true);
    return query.data ?? [];
  }, [scope, bookId, bookQuery.data, query.data]);

  // Client-side facet narrowing over the fetched page (cheap; server already did
  // the scope/q filter). Derived — recomputed only when inputs change.
  const motifs = useMemo<Motif[]>(() => {
    const all = baseData;
    return all.filter((m) => {
      if (facets.kind && m.kind !== facets.kind) return false;
      if (facets.genre && !m.genre_tags.includes(facets.genre)) return false;
      if (facets.tension != null && m.tension_target !== facets.tension) return false;
      if (facets.tier) {
        const tier = m.owner_user_id == null ? 'system' : (m.visibility === 'public' ? 'public' : 'user');
        if (tier !== facets.tier) return false;
      }
      return true;
    });
  }, [query.data, facets]);

  const setFacet = <K extends keyof MotifFacets>(k: K, v: MotifFacets[K]) =>
    setFacets((prev) => ({ ...prev, [k]: prev[k] === v ? undefined : v }));
  const clearFacets = () => setFacets({});

  // The available facet values (derived from the fetched page — only show filters
  // that would actually match something).
  const available = useMemo(() => {
    const all = baseData;
    const genres = new Set<string>();
    const kinds = new Set<MotifKind>();
    for (const m of all) {
      m.genre_tags.forEach((g) => genres.add(g));
      kinds.add(m.kind);
    }
    return { genres: [...genres].sort(), kinds: [...kinds].sort() };
  }, [baseData]);

  const isEmpty = !query.isLoading && !query.isError && motifs.length === 0 && baseData.length === 0;

  return {
    motifs,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    isEmpty,
    scope, setScope,
    search, setSearch,
    facets, setFacet, clearFacets,
    available,
    rawCount: baseData.length,
    hasBook: !!bookId,
  };
}
