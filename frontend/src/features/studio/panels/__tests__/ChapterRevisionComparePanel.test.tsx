// #20_agent_mode.md D2 — the `chapter-revision-compare` params-retargeting
// singleton wrapping the EXISTING RevisionCompareView AS-IS. Stubs
// RevisionCompareView (its own diff-rendering logic is covered by its own
// tests) so this stays a focused test of THIS panel's param-resolution,
// retargeting, and self-titling wiring — same shape as
// TranslationVersionsPanel.test.tsx.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

vi.mock('@/features/books/components/RevisionCompareView', () => ({
  RevisionCompareView: (props: {
    bookId: string; chapterId: string; initialLeftId?: string; initialRightId?: string; showBackLink?: boolean;
  }) => (
    <div
      data-testid="stub-revision-compare-view"
      data-book={props.bookId}
      data-chapter={props.chapterId}
      data-left={props.initialLeftId ?? ''}
      data-right={props.initialRightId ?? ''}
      data-back={String(props.showBackLink)}
    />
  ),
}));

import { ChapterRevisionComparePanel } from '../ChapterRevisionComparePanel';

function dockProps(params?: Record<string, unknown>) {
  let handler: ((next: Record<string, unknown> | undefined) => void) | null = null;
  const api = {
    setTitle: vi.fn(),
    onDidParametersChange: (cb: (next: Record<string, unknown> | undefined) => void) => {
      handler = cb;
      return { dispose: () => { handler = null; } };
    },
    updateParameters: (next: Record<string, unknown>) => handler?.(next),
  };
  return { api, params } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}>{ui}</StudioHostProvider>);
}

describe('ChapterRevisionComparePanel', () => {
  it('renders the empty state with no chapterId param', () => {
    withHost('b1', <ChapterRevisionComparePanel {...dockProps()} />);
    expect(screen.getByTestId('studio-chapter-revision-compare-panel').textContent).toContain(
      "Open a chapter's revision diff from Agent Mode's review panel.",
    );
    expect(screen.queryByTestId('stub-revision-compare-view')).toBeNull();
  });

  it('resolves bookId from the host and passes chapterId/fromRevisionId/toRevisionId through, hiding the classic back-link (DOCK-7)', () => {
    withHost('b1', <ChapterRevisionComparePanel {...dockProps({ chapterId: 'ch1', fromRevisionId: 'pre1', toRevisionId: 'post1' })} />);
    const stub = screen.getByTestId('stub-revision-compare-view');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(stub.getAttribute('data-chapter')).toBe('ch1');
    expect(stub.getAttribute('data-left')).toBe('pre1');
    expect(stub.getAttribute('data-right')).toBe('post1');
    expect(stub.getAttribute('data-back')).toBe('false');
  });

  it('retargets to a new chapter/revision pair via onDidParametersChange (no new panel instance needed)', async () => {
    const props = dockProps({ chapterId: 'ch1', fromRevisionId: 'pre1', toRevisionId: 'post1' });
    withHost('b1', <ChapterRevisionComparePanel {...props} />);
    expect(screen.getByTestId('stub-revision-compare-view').getAttribute('data-chapter')).toBe('ch1');

    (props.api as unknown as { updateParameters: (n: Record<string, unknown>) => void })
      .updateParameters({ chapterId: 'ch2', fromRevisionId: 'preA', toRevisionId: 'postA' });

    await waitFor(() => {
      const stub = screen.getByTestId('stub-revision-compare-view');
      expect(stub.getAttribute('data-chapter')).toBe('ch2');
      expect(stub.getAttribute('data-left')).toBe('preA');
      expect(stub.getAttribute('data-right')).toBe('postA');
    });
  });

  it('sets the dock tab title with a chapter suffix', () => {
    const props = dockProps({ chapterId: '0199aabbccdd' });
    withHost('b1', <ChapterRevisionComparePanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalledWith('Chapter Revision Compare · 0199aabb');
  });
});
