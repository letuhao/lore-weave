import { describe, it, expect, vi, beforeEach } from 'vitest';
import { glossaryApi } from '@/features/glossary/api';
import { wikiApi } from '@/features/wiki/api';
import { enrichmentApi } from '@/features/enrichment/api';
import {
  fetchProposalInbox,
  proposalDeepLink,
} from '../proposalsInbox';

// C11 — the 3 source-fetch adapters + normalized row model. The inbox merges
// all 3 sources into one list; each row carries its origin + the correct
// deep-link; a failing/empty source degrades gracefully (others still render).

const BOOK = 'book-1';
const TOK = 'tok';

function glossaryDraft(id: string, name: string) {
  return {
    entity_id: id,
    book_id: BOOK,
    kind_id: 'k',
    kind: { kind_id: 'k', code: 'item', name: 'Item', icon: '', color: '#000' },
    display_name: name,
    display_name_translation: null,
    status: 'draft' as const,
    tags: ['ai-suggested'],
    chapter_link_count: 0,
    translation_count: 0,
    evidence_count: 0,
    created_at: '',
    updated_at: '',
  };
}

function wikiSuggestion(id: string, name: string) {
  return {
    suggestion_id: id,
    article_id: 'a-' + id,
    user_id: 'u',
    diff_json: {},
    reason: 'ai-regen',
    status: 'pending',
    reviewer_note: null,
    created_at: '',
    reviewed_at: null,
    article_display_name: name,
  };
}

function proposal(id: string, name: string, reviewStatus: string) {
  return {
    proposal_id: id,
    job_id: 'j',
    project_id: 'p',
    user_id: 'u',
    entity_kind: 'character',
    target_ref: name,
    canonical_name: name,
    content: 'c',
    origin: 'enrichment',
    technique: 'rag',
    provenance_json: {},
    confidence: 0.8,
    source_refs_json: [],
    cultural_grounding_ref_id: null,
    review_status: reviewStatus,
    writeback_entity_id: null,
    promoted_entity_id: null,
    promoted_by: null,
    promoted_at: null,
    promoted_from_proposal_id: null,
    original_technique: null,
    rejected_reason: null,
    created_at: '',
    updated_at: '',
  };
}

const okList = <T,>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });

describe('fetchProposalInbox', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('merges all 3 sources into one list with correct origins + deep-links', async () => {
    vi.spyOn(glossaryApi, 'listAiSuggestions').mockResolvedValue(
      okList([glossaryDraft('g1', '九天明帝经')]) as never,
    );
    vi.spyOn(wikiApi, 'listSuggestions').mockResolvedValue(
      okList([wikiSuggestion('w1', '张若尘')]) as never,
    );
    vi.spyOn(enrichmentApi, 'listProposals').mockImplementation(
      async (_b, params) =>
        okList(
          params.review_status === 'proposed'
            ? [proposal('p1', '林妃', 'proposed')]
            : [proposal('p2', '神武印记', 'author_reviewing')],
        ) as never,
    );

    const inbox = await fetchProposalInbox(BOOK, TOK);

    // all 3 sources present, all merged
    expect(inbox.rows).toHaveLength(4);
    const byOrigin = (o: string) => inbox.rows.filter((r) => r.origin === o);
    expect(byOrigin('glossary')).toHaveLength(1);
    expect(byOrigin('wiki')).toHaveLength(1);
    expect(byOrigin('enrichment')).toHaveLength(2); // both review_status calls merged

    // each row deep-links to its source's existing review UI
    expect(byOrigin('glossary')[0].deepLinkUrl).toBe(proposalDeepLink.glossary(BOOK));
    expect(byOrigin('wiki')[0].deepLinkUrl).toBe(proposalDeepLink.wiki(BOOK));
    expect(byOrigin('enrichment')[0].deepLinkUrl).toBe(proposalDeepLink.enrichment(BOOK));

    // titles carry the source name
    expect(byOrigin('glossary')[0].title).toBe('九天明帝经');
  });

  it('fetches glossary drafts with the status=draft & tags=ai-suggested filter', async () => {
    const spy = vi
      .spyOn(glossaryApi, 'listAiSuggestions')
      .mockResolvedValue(okList([]) as never);
    vi.spyOn(wikiApi, 'listSuggestions').mockResolvedValue(okList([]) as never);
    vi.spyOn(enrichmentApi, 'listProposals').mockResolvedValue(okList([]) as never);

    await fetchProposalInbox(BOOK, TOK);

    // listAiSuggestions encodes status=draft&tags=ai-suggested internally —
    // the adapter must use it (not a raw listEntities with a broader filter).
    expect(spy).toHaveBeenCalledWith(BOOK, TOK);
  });

  it('fetches wiki suggestions with the status=pending filter (the review queue)', async () => {
    vi.spyOn(glossaryApi, 'listAiSuggestions').mockResolvedValue(okList([]) as never);
    const spy = vi
      .spyOn(wikiApi, 'listSuggestions')
      .mockResolvedValue(okList([]) as never);
    vi.spyOn(enrichmentApi, 'listProposals').mockResolvedValue(okList([]) as never);

    await fetchProposalInbox(BOOK, TOK);

    // the wiki review inbox is wiki_suggestions filtered to status='pending'
    // (NOT an article 'stub' status — that does not exist).
    expect(spy).toHaveBeenCalledWith(
      BOOK,
      expect.objectContaining({ status: 'pending' }),
      TOK,
    );
  });

  it('fetches enrichment with review_status=proposed AND author_reviewing (two exact-match calls)', async () => {
    vi.spyOn(glossaryApi, 'listAiSuggestions').mockResolvedValue(okList([]) as never);
    vi.spyOn(wikiApi, 'listSuggestions').mockResolvedValue(okList([]) as never);
    const spy = vi
      .spyOn(enrichmentApi, 'listProposals')
      .mockResolvedValue(okList([]) as never);

    await fetchProposalInbox(BOOK, TOK);

    const statuses = spy.mock.calls.map((c) => c[1].review_status);
    expect(statuses).toContain('proposed');
    expect(statuses).toContain('author_reviewing');
    // exactly the two pending-review states — no over-broad query
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('degrades gracefully when one source errors — others still render', async () => {
    vi.spyOn(glossaryApi, 'listAiSuggestions').mockResolvedValue(
      okList([glossaryDraft('g1', 'A')]) as never,
    );
    // wiki source down
    vi.spyOn(wikiApi, 'listSuggestions').mockRejectedValue(new Error('wiki 503'));
    vi.spyOn(enrichmentApi, 'listProposals').mockResolvedValue(
      okList([proposal('p1', 'B', 'proposed')]) as never,
    );

    const inbox = await fetchProposalInbox(BOOK, TOK);

    // the failing source did NOT blank the inbox
    expect(inbox.rows.some((r) => r.origin === 'glossary')).toBe(true);
    expect(inbox.rows.some((r) => r.origin === 'enrichment')).toBe(true);
    // the down source reports its error + zero rows
    const wiki = inbox.sources.find((s) => s.origin === 'wiki')!;
    expect(wiki.error).toBeInstanceOf(Error);
    expect(wiki.rows).toHaveLength(0);
    // healthy sources have no error
    expect(inbox.sources.find((s) => s.origin === 'glossary')!.error).toBeNull();
  });

  it('renders an empty source without error (graceful empty)', async () => {
    vi.spyOn(glossaryApi, 'listAiSuggestions').mockResolvedValue(okList([]) as never);
    vi.spyOn(wikiApi, 'listSuggestions').mockResolvedValue(
      okList([wikiSuggestion('w1', 'X')]) as never,
    );
    vi.spyOn(enrichmentApi, 'listProposals').mockResolvedValue(okList([]) as never);

    const inbox = await fetchProposalInbox(BOOK, TOK);

    const glossary = inbox.sources.find((s) => s.origin === 'glossary')!;
    expect(glossary.error).toBeNull();
    expect(glossary.rows).toHaveLength(0);
    // the populated source still renders
    expect(inbox.rows.some((r) => r.origin === 'wiki')).toBe(true);
  });
});
