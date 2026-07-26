import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { KnowledgeIndexControl } from '../components/KnowledgeIndexControl';
import editorEn from '@/i18n/locales/en/editor.json';

/**
 * WS-0.9 — the "Add to knowledge" control.
 *
 * Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md.
 *
 * This is the user-visible half of publish-independent indexing. Publishing no longer
 * puts a chapter in the knowledge graph, so without this control there is literally no
 * way for a user to get a draft chapter into their KG — and no way to SEE what is in it.
 */

const h = vi.hoisted(() => ({
  indexChapter: vi.fn(),
  setChapterKgExclude: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/features/books/api', () => ({
  booksApi: {
    indexChapter: (...a: unknown[]) => h.indexChapter(...a),
    setChapterKgExclude: (...a: unknown[]) => h.setChapterKgExclude(...a),
  },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('sonner', () => ({
  toast: { success: (m: string) => h.toastSuccess(m), error: (m: string) => h.toastError(m) },
}));

const renderControl = (over: Record<string, unknown> = {}) => {
  const onChanged = vi.fn();
  const utils = render(
    <KnowledgeIndexControl
      token="tok"
      bookId="b1"
      chapterId="c1"
      onChanged={onChanged}
      {...over}
    />,
  );
  return { ...utils, onChanged };
};

beforeEach(() => {
  vi.clearAllMocks();
  h.indexChapter.mockResolvedValue({ chapter_id: 'c1', revision_id: 'r1', reused_revision: false });
  h.setChapterKgExclude.mockResolvedValue({ chapter_id: 'c1', kg_exclude: true });
});

describe('KnowledgeIndexControl', () => {
  it('THE POINT: a DRAFT chapter can be added to the knowledge graph', async () => {
    // Never published (no editorial status involved at all) and not yet indexed.
    const { onChanged } = renderControl({ kgIndexedRevisionId: null, kgExclude: false });

    expect(screen.getByTestId('knowledge-badge')).toHaveAttribute('data-kg-state', 'not-indexed');

    fireEvent.click(screen.getByTestId('knowledge-index-button'));

    await waitFor(() => expect(h.indexChapter).toHaveBeenCalledWith('tok', 'b1', 'c1'));
    expect(h.toastSuccess).toHaveBeenCalledWith('knowledge.indexed_toast');
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('shows the indexed state — the user must be able to SEE what is in their graph', () => {
    renderControl({ kgIndexedRevisionId: 'rev-1', kgExclude: false });

    expect(screen.getByTestId('knowledge-badge')).toHaveAttribute('data-kg-state', 'indexed');
    // Re-index, not "add" — it is already there.
    expect(screen.getByTestId('knowledge-index-button')).toHaveTextContent('knowledge.reindex');
    // And it can be forgotten.
    expect(screen.getByTestId('knowledge-forget-button')).toBeInTheDocument();
  });

  it('re-indexing an UNCHANGED draft says "nothing changed" — no silent fake success', async () => {
    h.indexChapter.mockResolvedValue({ chapter_id: 'c1', revision_id: 'r1', reused_revision: true });
    renderControl({ kgIndexedRevisionId: 'rev-1', kgExclude: false });

    fireEvent.click(screen.getByTestId('knowledge-index-button'));

    await waitFor(() => expect(h.toastSuccess).toHaveBeenCalledWith('knowledge.reused_toast'));
    // NOT the "added" toast — implying fresh work happened would be a lie.
    expect(h.toastSuccess).not.toHaveBeenCalledWith('knowledge.indexed_toast');
  });

  it('an EXCLUDED chapter offers only "allow" — not a button that cannot work', () => {
    renderControl({ kgIndexedRevisionId: null, kgExclude: true });

    expect(screen.getByTestId('knowledge-badge')).toHaveAttribute('data-kg-state', 'excluded');
    expect(screen.getByTestId('knowledge-allow-button')).toBeInTheDocument();
    // kg_exclude is producer-side authoritative: an "Add" here would just 409.
    expect(screen.queryByTestId('knowledge-index-button')).not.toBeInTheDocument();
  });

  it('allowing does NOT silently re-index — re-entering the graph is an explicit act', async () => {
    renderControl({ kgIndexedRevisionId: null, kgExclude: true });

    fireEvent.click(screen.getByTestId('knowledge-allow-button'));

    await waitFor(() =>
      expect(h.setChapterKgExclude).toHaveBeenCalledWith('tok', 'b1', 'c1', false),
    );
    // A toggle that silently re-ingests the user's prose is a privacy surprise.
    expect(h.indexChapter).not.toHaveBeenCalled();
    expect(h.toastSuccess).toHaveBeenCalledWith('knowledge.allowed_toast');
  });

  it('"forget" is confirm-gated and RETRACTS', async () => {
    const { onChanged } = renderControl({ kgIndexedRevisionId: 'rev-1', kgExclude: false });

    fireEvent.click(screen.getByTestId('knowledge-forget-button'));
    // Not fired until confirmed.
    expect(h.setChapterKgExclude).not.toHaveBeenCalled();

    fireEvent.click(await screen.findByRole('button', { name: 'knowledge.forget' }));

    await waitFor(() =>
      expect(h.setChapterKgExclude).toHaveBeenCalledWith('tok', 'b1', 'c1', true),
    );
    expect(h.toastSuccess).toHaveBeenCalledWith('knowledge.forgotten_toast');
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('review-impl: a chapter can be kept out BEFORE it is ever indexed', async () => {
    // The opt-out used to be gated behind isIndexed. But publishing AUTO-indexes a
    // chapter, so a user who wanted to keep one out of their knowledge graph had no way
    // to say so in advance — they had to let it in, then take it out.
    const { onChanged } = renderControl({ kgIndexedRevisionId: null, kgExclude: false });

    const btn = screen.getByTestId('knowledge-forget-button');
    expect(btn).toHaveTextContent('knowledge.keep_out'); // not "forget" — nothing to forget yet

    fireEvent.click(btn);
    fireEvent.click(await screen.findByRole('button', { name: 'knowledge.forget' }));

    await waitFor(() =>
      expect(h.setChapterKgExclude).toHaveBeenCalledWith('tok', 'b1', 'c1', true),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('a dirty editor blocks indexing (it would pin the STALE server draft)', () => {
    renderControl({ kgIndexedRevisionId: null, kgExclude: false, dirty: true });
    expect(screen.getByTestId('knowledge-index-button')).toBeDisabled();
  });

  it('an excluded-chapter failure names the REASON, not a generic error', async () => {
    h.indexChapter.mockRejectedValue({ code: 'BOOK_KG_EXCLUDED' });
    renderControl({ kgIndexedRevisionId: null, kgExclude: false });

    fireEvent.click(screen.getByTestId('knowledge-index-button'));

    await waitFor(() => expect(h.toastError).toHaveBeenCalledWith('knowledge.excluded_toast'));
  });
});

describe('vocabulary (S06 jargon deny-list)', () => {
  it('never says index / extract / canon / revision to the user', () => {
    const k = (editorEn as Record<string, Record<string, string>>).knowledge;
    const banned = ['index', 'extract', 'canon', 'revision', 'kg', 'graph node', 'embedding'];
    for (const [key, copy] of Object.entries(k)) {
      const lower = copy.toLowerCase();
      for (const word of banned) {
        expect(
          lower.includes(word),
          `editor.knowledge.${key} leaks jargon "${word}": ${copy}`,
        ).toBe(false);
      }
    }
  });

  it('the unpublish dialog no longer claims it retracts knowledge (WS-0.8 made that FALSE)', () => {
    const body = (editorEn as Record<string, Record<string, string>>).publish.confirm_body.toLowerCase();
    expect(body).not.toContain('retract');
    // Unpublish is editorial only now — the knowledge survives it.
    expect(body).toContain('knowledge');
  });
});
