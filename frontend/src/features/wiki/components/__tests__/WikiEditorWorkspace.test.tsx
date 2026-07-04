// 15_wiki_panels.md B2b — the shared dirty-guard: Back (and the "article not found" fallback)
// must not silently discard an unsaved draft. This is a genuine regression risk (the classic
// page's Back button had NO guard at all before this migration — client-side navigate() doesn't
// fire beforeunload). Both the page and the studio panel route through `onBack`, so this test
// covers both callers at once.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { WikiArticleDetail } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => (o?.defaultValue as string) ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/components/editor/TiptapEditor', () => ({
  TiptapEditor: ({ onUpdate }: { onUpdate: (json: unknown) => void }) => (
    <button onClick={() => onUpdate({ content: [{ type: 'paragraph' }] })}>stub-editor-type</button>
  ),
}));
vi.mock('../WikiSuggestionReview', () => ({ WikiSuggestionReview: () => <div /> }));

const article: WikiArticleDetail = {
  article_id: 'a1', entity_id: 'e1', book_id: 'b1', display_name: 'Mina',
  kind: { kind_id: 'k', code: 'character', name: 'Character', icon: '', color: '#abc' },
  status: 'draft', template_code: null, revision_count: 1,
  updated_at: '2026-06-11T00:00:00Z', body_json: { content: [] },
  spoiler_chapters: [], infobox: [], created_at: '2026-06-11T00:00:00Z',
};

const getArticle = vi.fn();
const listRevisions = vi.fn();
const listSuggestions = vi.fn();
vi.mock('../../api', () => ({
  wikiApi: {
    getArticle: (...a: unknown[]) => getArticle(...a),
    listRevisions: (...a: unknown[]) => listRevisions(...a),
    listSuggestions: (...a: unknown[]) => listSuggestions(...a),
    patchArticle: vi.fn(),
    deleteArticle: vi.fn(),
  },
}));

import { WikiEditorWorkspace } from '../WikiEditorWorkspace';

function setup(onBack = vi.fn(), onDirtyChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <WikiEditorWorkspace bookId="b1" articleId="a1" onBack={onBack} onDirtyChange={onDirtyChange} />
    </QueryClientProvider>,
  );
  return { ...utils, onBack, onDirtyChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  getArticle.mockResolvedValue(article);
  listRevisions.mockResolvedValue({ items: [] });
  listSuggestions.mockResolvedValue({ items: [] });
});

describe('WikiEditorWorkspace — B2b dirty-guard', () => {
  it('Back leaves immediately when there are no unsaved edits', async () => {
    const { onBack } = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('Back'));
    expect(onBack).toHaveBeenCalled();
  });

  it('Back is gated behind a confirm when there are unsaved edits — cancel keeps you on the page', async () => {
    const { onBack, onDirtyChange } = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));

    fireEvent.click(screen.getByText('Back'));
    expect(onBack).not.toHaveBeenCalled();
    expect(await screen.findByText('Discard unsaved changes?')).toBeTruthy();

    // Cancel — must NOT navigate away.
    fireEvent.click(screen.getByText('Cancel'));
    expect(onBack).not.toHaveBeenCalled();
  });

  it('Back confirm discards and leaves', async () => {
    const { onBack } = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    fireEvent.click(screen.getByText('Back'));
    fireEvent.click(await screen.findByText('Discard & leave'));
    expect(onBack).toHaveBeenCalled();
  });

  it('a fresh save clears dirty (bubbled via onDirtyChange) so Back no longer needs confirming', async () => {
    const { wikiApi } = await import('../../api');
    (wikiApi.patchArticle as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const { onBack, onDirtyChange } = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));

    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));

    fireEvent.click(screen.getByText('Back'));
    expect(onBack).toHaveBeenCalled();
  });
});
