import { glossaryApi } from '@/features/glossary/api';
import { wikiApi } from '@/features/wiki/api';
import { enrichmentApi } from '@/features/enrichment/api';

// C11 (C11-proposals-inbox) — the 3 source-fetch adapters + the normalized
// row model for the Pending Proposals inbox.
//
// INTEGRATE, don't duplicate (LOCKED): the inbox aggregates EXACTLY 3
// existing review queues read-only and DEEP-LINKS each row to that source's
// OWN review UI. No in-knowledge approve/reject/edit, no new BE store.
//
// The 3 sources (all book-scoped — the inbox resolves bookId from the
// route-scoped project, G6):
//   1. glossary AI-suggested drafts  → status=draft & tags=ai-suggested
//      (glossaryApi.listAiSuggestions hard-codes that exact filter).
//   2. AI wiki suggestions          → wiki_suggestions with status='pending'
//      (the wiki review inbox: AI-regen + community edits awaiting a
//      human accept/reject — listSuggestions filters ws.status exactly).
//   3. lore-enrichment proposals     → review_status ∈ {proposed,
//      author_reviewing}. The BE filters review_status by EXACT equality
//      (review.py:239 `p.review_status = $n`), so the pipe set is fetched as
//      TWO calls and merged here — NOT one `proposed|author_reviewing` param.
//
// Graceful degrade: each source is fetched independently; one source
// erroring (or empty) must NOT blank the others. fetchProposalInbox returns
// a per-source result carrying either its rows or its error.

export type ProposalOrigin = 'glossary' | 'wiki' | 'enrichment';

/** The normalized inbox row — the ONLY shape the UI renders. */
export interface ProposalInboxRow {
  /** Stable per-row id (the source entity/article/proposal id). */
  id: string;
  origin: ProposalOrigin;
  /** Human-facing label for the row (entity / article / proposal name). */
  title: string;
  /** Deep-link to the source's EXISTING review UI route (book-scoped). */
  deepLinkUrl: string;
}

/** One source's fetch outcome — rows on success, error on failure. The UI
 *  reads `error` to show a per-source error chip while still rendering the
 *  other sources (graceful degrade). */
export interface ProposalSourceResult {
  origin: ProposalOrigin;
  rows: ProposalInboxRow[];
  error: Error | null;
}

export interface ProposalInbox {
  sources: ProposalSourceResult[];
  /** Flat merged list across all successful sources. */
  rows: ProposalInboxRow[];
}

// ── Deep-link builders (each row links to its source's existing review UI) ──
// glossary drafts   → the book's Glossary tab (draft-review surface);
// wiki suggestions  → the book's Wiki tab (the article view surfaces its
//                     pending suggestions with accept/reject);
// enrichment        → the book's Enrichment tab (ProposalsPanel review surface).
export const proposalDeepLink = {
  glossary: (bookId: string) => `/books/${bookId}/glossary`,
  // The wiki tab is the suggestion-review surface (its article view lists the
  // article's pending suggestions with accept/reject). Article selection there
  // is internal state, NOT a route param — `/books/{id}/wiki/{articleId}` is
  // the EDITOR, not the review surface — so the row links to the tab, which is
  // the closest addressable review route.
  wiki: (bookId: string) => `/books/${bookId}/wiki`,
  enrichment: (bookId: string) => `/books/${bookId}/enrichment`,
} as const;

// lore-enrichment review_status set — both pending-review states. Fetched as
// separate calls because the BE matches review_status by exact equality.
const ENRICHMENT_REVIEW_STATUSES = ['proposed', 'author_reviewing'] as const;

function toError(e: unknown): Error {
  return e instanceof Error ? e : new Error(String(e));
}

async function fetchGlossarySource(
  bookId: string,
  token: string,
): Promise<ProposalSourceResult> {
  try {
    const resp = await glossaryApi.listAiSuggestions(bookId, token);
    const rows = (resp.items ?? []).map<ProposalInboxRow>((e) => ({
      id: e.entity_id,
      origin: 'glossary',
      title: e.display_name || e.entity_id,
      deepLinkUrl: proposalDeepLink.glossary(bookId),
    }));
    return { origin: 'glossary', rows, error: null };
  } catch (e) {
    return { origin: 'glossary', rows: [], error: toError(e) };
  }
}

async function fetchWikiSource(
  bookId: string,
  token: string,
): Promise<ProposalSourceResult> {
  try {
    // The wiki review queue is wiki_suggestions filtered to status='pending'
    // (a suggestion status — wiki articles have no stub/review status). Each
    // pending suggestion is a reviewable AI-regen / community edit.
    const resp = await wikiApi.listSuggestions(
      bookId,
      { status: 'pending', limit: 200 },
      token,
    );
    const rows = (resp.items ?? []).map<ProposalInboxRow>((s) => ({
      id: s.suggestion_id,
      origin: 'wiki',
      title: s.article_display_name || s.reason || s.suggestion_id,
      deepLinkUrl: proposalDeepLink.wiki(bookId),
    }));
    return { origin: 'wiki', rows, error: null };
  } catch (e) {
    return { origin: 'wiki', rows: [], error: toError(e) };
  }
}

async function fetchEnrichmentSource(
  bookId: string,
  token: string,
): Promise<ProposalSourceResult> {
  try {
    // Two calls (one per review_status) — the BE filters by exact equality,
    // so a single `proposed|author_reviewing` would match neither.
    const responses = await Promise.all(
      ENRICHMENT_REVIEW_STATUSES.map((rs) =>
        enrichmentApi.listProposals(bookId, { review_status: rs, limit: 100 }, token),
      ),
    );
    const seen = new Set<string>();
    const rows: ProposalInboxRow[] = [];
    for (const resp of responses) {
      for (const p of resp.items ?? []) {
        if (seen.has(p.proposal_id)) continue;
        seen.add(p.proposal_id);
        rows.push({
          id: p.proposal_id,
          origin: 'enrichment',
          title: p.canonical_name || p.target_ref || p.proposal_id,
          deepLinkUrl: proposalDeepLink.enrichment(bookId),
        });
      }
    }
    return { origin: 'enrichment', rows, error: null };
  } catch (e) {
    return { origin: 'enrichment', rows: [], error: toError(e) };
  }
}

/**
 * Fetch all 3 sources independently and merge into one inbox. Each source is
 * fetched in isolation (a per-source try/catch — NOT Promise.all rejecting the
 * batch), so one source erroring leaves the others intact (graceful degrade).
 */
export async function fetchProposalInbox(
  bookId: string,
  token: string,
): Promise<ProposalInbox> {
  const sources = await Promise.all([
    fetchGlossarySource(bookId, token),
    fetchWikiSource(bookId, token),
    fetchEnrichmentSource(bookId, token),
  ]);
  const rows = sources.flatMap((s) => s.rows);
  return { sources, rows };
}
