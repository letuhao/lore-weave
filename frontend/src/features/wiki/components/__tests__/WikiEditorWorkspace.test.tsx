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
  TiptapEditor: ({ content, onUpdate }: { content: unknown; onUpdate: (json: unknown) => void }) => (
    <div>
      <div data-testid="stub-editor-content">{JSON.stringify(content)}</div>
      <button onClick={() => onUpdate({ content: [{ type: 'paragraph', text: 'typed' }] })}>stub-editor-type</button>
    </div>
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
import { _resetWikiEditorDraftCache } from '../../lib/wikiEditorDraftCache';

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
  _resetWikiEditorDraftCache();
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

// 15_wiki_panels.md /review-impl — DOCK-10: dockview unmounts a closed panel (D4), so the
// panel-close vector was never covered by the G7 params-retargeting guard. `unmount()` here
// simulates the dock tab closing (a real remount, not just a re-render) — proving the fix
// actually survives a real unmount/mount cycle, not just an in-memory prop change.
describe('WikiEditorWorkspace — DOCK-10 draft survives a dock-tab close', () => {
  it('an unsaved edit is restored (dirty=true, editor content repopulated) after unmount + fresh mount of the SAME article', async () => {
    const first = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    await waitFor(() => expect(first.onDirtyChange).toHaveBeenCalledWith(true));
    first.unmount();

    const second = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    expect(second.onDirtyChange).toHaveBeenCalledWith(true);
    expect(screen.getByTestId('stub-editor-content').textContent).toContain('typed');
  });

  it('a DIFFERENT article never sees another article\'s cached draft', async () => {
    const first = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    await waitFor(() => expect(first.onDirtyChange).toHaveBeenCalledWith(true));
    first.unmount();

    const otherArticle = { ...article, article_id: 'a2', display_name: 'Lucy' };
    getArticle.mockResolvedValue(otherArticle);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onDirtyChange = vi.fn();
    render(
      <QueryClientProvider client={qc}>
        <WikiEditorWorkspace bookId="b1" articleId="a2" onBack={vi.fn()} onDirtyChange={onDirtyChange} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getAllByText('Lucy').length).toBeGreaterThan(0));
    expect(onDirtyChange).not.toHaveBeenCalledWith(true);
    expect(screen.getByTestId('stub-editor-content').textContent).not.toContain('typed');
  });

  it('a successful save clears the cache — reopening afterward does NOT resurrect the old draft', async () => {
    const { wikiApi } = await import('../../api');
    (wikiApi.patchArticle as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const first = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    await waitFor(() => expect(first.onDirtyChange).toHaveBeenCalledWith(true));
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(first.onDirtyChange).toHaveBeenLastCalledWith(false));
    first.unmount();

    const second = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    expect(second.onDirtyChange).not.toHaveBeenCalledWith(true);
  });

  it('discarding via the Back-confirm clears the cache — reopening does NOT resurrect the discarded draft', async () => {
    const first = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText('stub-editor-type'));
    await waitFor(() => expect(first.onDirtyChange).toHaveBeenCalledWith(true));
    fireEvent.click(screen.getByText('Back'));
    fireEvent.click(await screen.findByText('Discard & leave'));
    first.unmount();

    const second = setup();
    await waitFor(() => expect(screen.getAllByText('Mina').length).toBeGreaterThan(0));
    expect(second.onDirtyChange).not.toHaveBeenCalledWith(true);
  });
});
