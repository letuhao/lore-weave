// 15_wiki_panels.md B2b — the G7 dirty-guard: retargeting `wiki-editor` to a different
// articleId while the workspace reports itself dirty must NOT silently discard the unsaved
// draft (JsonEditorPanel precedent: "dirty ⇒ never clobber — G7 spirit"). This is the single
// highest-risk finding from this migration's design review — a naive retargeting singleton
// would lose prose the instant a user opened a different article mid-edit.
import { act, render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
// The panel self-titles from the article's display_name (BookReaderPanel precedent — see the
// title-refinement race /review-impl found when this lived in a WikiEditorWorkspace callback
// instead). Not under test here; return nothing so the title effect simply no-ops.
vi.mock('@/features/wiki/api', () => ({ wikiApi: { getArticle: () => new Promise(() => {}) } }));

// /review-impl DOCK-10 fix — a confirmed discard-and-switch must also clear the survives-a-
// tab-close draft cache, else reopening the OLD article later would resurrect the very draft
// the user just explicitly discarded. WikiEditorWorkspace is stubbed in this file, so the cache
// itself is exercised end-to-end by WikiEditorWorkspace.test.tsx instead — this just proves the
// panel calls the clear function at the right moment.
const clearWikiEditorDraft = vi.fn();
vi.mock('@/features/wiki/lib/wikiEditorDraftCache', () => ({
  clearWikiEditorDraft: () => clearWikiEditorDraft(),
}));

// A minimal stub standing in for the real workspace: exposes onDirtyChange/onBack as buttons
// so the test can drive them directly, and surfaces its own articleId/initialRightPanel props
// so a `key`-forced remount on a confirmed switch is directly observable.
vi.mock('@/features/wiki/components/WikiEditorWorkspace', () => ({
  WikiEditorWorkspace: ({ articleId, initialRightPanel, onBack, onDirtyChange }: {
    articleId: string;
    initialRightPanel?: string;
    onBack: () => void;
    onDirtyChange?: (d: boolean) => void;
  }) => (
    <div data-testid="stub-workspace" data-article-id={articleId} data-right-panel={initialRightPanel ?? ''}>
      <button onClick={() => onDirtyChange?.(true)}>make-dirty</button>
      <button onClick={onBack}>stub-back</button>
    </div>
  ),
}));

import { WikiEditorPanel } from '../WikiEditorPanel';

function dockProps(params?: Record<string, unknown>) {
  const listeners = new Set<(p: Record<string, unknown>) => void>();
  const props = {
    api: {
      setTitle: vi.fn(),
      onDidParametersChange: (cb: (p: Record<string, unknown>) => void) => {
        listeners.add(cb);
        return { dispose: () => listeners.delete(cb) };
      },
    },
    params,
  } as unknown as IDockviewPanelProps;
  return { props, fireParams: (p: Record<string, unknown>) => listeners.forEach((l) => l(p)) };
}

function withHost(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId="b1">{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

describe('WikiEditorPanel — G7 dirty-guard on retarget', () => {
  it('empty params: shows the affordance hint', () => {
    const { props } = dockProps();
    withHost(<WikiEditorPanel {...props} />);
    expect(screen.getByTestId('studio-wiki-editor-panel').textContent).toContain(
      'Open an article from the Wiki panel to edit it here.',
    );
  });

  it('renders the workspace for the given articleId', () => {
    const { props } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    expect(screen.getByTestId('stub-workspace').getAttribute('data-article-id')).toBe('a1');
  });

  it('retargets immediately when NOT dirty (no confirm needed)', () => {
    const { props, fireParams } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    act(() => { fireParams({ articleId: 'a2' }); });
    expect(screen.getByTestId('stub-workspace').getAttribute('data-article-id')).toBe('a2');
  });

  it('a rightPanel-only retarget (same article — e.g. the History button re-opening it) never needs the guard', () => {
    const { props, fireParams } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    fireEvent.click(screen.getByText('make-dirty'));
    act(() => { fireParams({ articleId: 'a1', rightPanel: 'history' }); });
    expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
    expect(screen.getByTestId('stub-workspace').getAttribute('data-right-panel')).toBe('history');
  });

  it('DIRTY + a different articleId stages the switch behind a confirm — the old article stays rendered until confirmed', () => {
    const { props, fireParams } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    fireEvent.click(screen.getByText('make-dirty'));

    act(() => { fireParams({ articleId: 'a2' }); });
    // Still showing a1 — the swap has NOT happened yet.
    expect(screen.getByTestId('stub-workspace').getAttribute('data-article-id')).toBe('a1');
    expect(screen.getByText('Discard unsaved changes?')).toBeTruthy();
  });

  it('canceling the confirm keeps the original article mounted (no data loss)', () => {
    const { props, fireParams } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    fireEvent.click(screen.getByText('make-dirty'));
    act(() => { fireParams({ articleId: 'a2' }); });

    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.getByTestId('stub-workspace').getAttribute('data-article-id')).toBe('a1');
    expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
  });

  it('confirming discards and switches to the new article', () => {
    const { props, fireParams } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    fireEvent.click(screen.getByText('make-dirty'));
    act(() => { fireParams({ articleId: 'a2' }); });

    fireEvent.click(screen.getByText('Discard & switch'));
    expect(screen.getByTestId('stub-workspace').getAttribute('data-article-id')).toBe('a2');
    expect(clearWikiEditorDraft).toHaveBeenCalled();
  });

  it('onBack opens the sibling wiki panel', () => {
    const { props } = dockProps({ articleId: 'a1' });
    withHost(<WikiEditorPanel {...props} />);
    // No dock api attached in this test harness — openPanel is a documented no-op until one
    // is; the real assertion is that clicking doesn't throw (StepConfig.test.tsx precedent).
    expect(() => fireEvent.click(screen.getByText('stub-back'))).not.toThrow();
  });
});
