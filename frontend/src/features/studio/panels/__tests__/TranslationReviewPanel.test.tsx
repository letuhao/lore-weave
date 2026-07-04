// TranslationReviewPanel — params-retargeting singleton ({bookId, chapterId, versionId}), same
// precedent as TranslationVersionsPanel/OriginalSourcePanel: empty state with no target, retarget
// via onDidParametersChange, self-titles with a chapter suffix. onVersionSwitch re-targets the
// SAME dock id via host.openPanel instead of navigating. TranslationReviewView's own review logic
// (AC4 banner, block correction, etc.) is covered by its own consumer (TranslationReviewPage) —
// this test stays about THIS panel's own wiring.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const openPanel = vi.fn();
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => ({ bookId: 'b1', openPanel }) }));

vi.mock('@/features/translation/components/TranslationReviewView', () => ({
  TranslationReviewView: ({
    bookId, chapterId, versionId, onVersionSwitch,
  }: {
    bookId: string; chapterId: string; versionId: string; onVersionSwitch: (v: string) => void;
  }) => (
    <div data-testid="stub-translation-review-view" data-book={bookId} data-chapter={chapterId} data-version={versionId}>
      <button type="button" onClick={() => onVersionSwitch('v2')}>switch</button>
    </div>
  ),
}));

import { TranslationReviewPanel } from '../TranslationReviewPanel';

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

describe('TranslationReviewPanel', () => {
  it('renders the empty state with no target params', () => {
    render(<TranslationReviewPanel {...dockProps()} />);
    expect(screen.getByTestId('studio-translation-review').textContent).toContain(
      "Open a version's Review from the Translation Versions panel.",
    );
    expect(screen.queryByTestId('stub-translation-review-view')).toBeNull();
  });

  it('renders TranslationReviewView with the target params', () => {
    render(<TranslationReviewPanel {...dockProps({ bookId: 'b1', chapterId: 'ch1', versionId: 'v1' })} />);
    const stub = screen.getByTestId('stub-translation-review-view');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(stub.getAttribute('data-chapter')).toBe('ch1');
    expect(stub.getAttribute('data-version')).toBe('v1');
  });

  it('retargets to a new versionId via onDidParametersChange', async () => {
    const props = dockProps({ bookId: 'b1', chapterId: 'ch1', versionId: 'v1' });
    render(<TranslationReviewPanel {...props} />);
    (props.api as unknown as { updateParameters: (n: Record<string, unknown>) => void })
      .updateParameters({ bookId: 'b1', chapterId: 'ch1', versionId: 'v2' });
    await waitFor(() => {
      expect(screen.getByTestId('stub-translation-review-view').getAttribute('data-version')).toBe('v2');
    });
  });

  it('sets the dock tab title with a chapter suffix', () => {
    const props = dockProps({ bookId: 'b1', chapterId: '0199aabbccdd', versionId: 'v1' });
    render(<TranslationReviewPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalledWith('Translation Review · 0199aabb');
  });

  it('onVersionSwitch re-targets the SAME dock id via host.openPanel (no navigation)', () => {
    openPanel.mockReset();
    render(<TranslationReviewPanel {...dockProps({ bookId: 'b1', chapterId: 'ch1', versionId: 'v1' })} />);
    fireEvent.click(screen.getByText('switch'));
    expect(openPanel).toHaveBeenCalledWith('translation-review:ch1', expect.objectContaining({
      component: 'translation-review',
      params: { bookId: 'b1', chapterId: 'ch1', versionId: 'v2' },
    }));
  });
});
