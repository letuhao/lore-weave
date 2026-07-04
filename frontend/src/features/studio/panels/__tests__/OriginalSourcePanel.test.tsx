// 16_chapter_editor_parity_and_retirement.md Phase 2 task 2.11 — OriginalSourcePanel: lazy
// fetch-once-per-target, loading state before resolution, retarget via onDidParametersChange
// re-fetches for a new chapterId (JsonEditorPanel retargeting precedent).
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const getOriginalContent = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { getOriginalContent: (...args: unknown[]) => getOriginalContent(...args) },
}));

import { OriginalSourcePanel } from '../OriginalSourcePanel';

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

describe('OriginalSourcePanel', () => {
  beforeEach(() => {
    getOriginalContent.mockReset();
  });

  it('renders the empty state with no bookId/chapterId', () => {
    render(<OriginalSourcePanel {...dockProps()} />);
    expect(screen.getByTestId('studio-original-source').textContent).toContain('Open a chapter from the Editor to view its original source.');
    expect(getOriginalContent).not.toHaveBeenCalled();
  });

  it('shows a loading skeleton before the fetch resolves, then renders numbered paragraphs', async () => {
    let resolveFetch: (v: string) => void = () => {};
    getOriginalContent.mockReturnValue(new Promise<string>((resolve) => { resolveFetch = resolve; }));

    render(<OriginalSourcePanel {...dockProps({ bookId: 'b1', chapterId: 'c1' })} />);

    expect(screen.getByTestId('original-source-loading')).toBeTruthy();
    expect(getOriginalContent).toHaveBeenCalledWith('tok', 'b1', 'c1');

    resolveFetch('First paragraph.\n\nSecond paragraph.');

    await waitFor(() => {
      expect(screen.queryByTestId('original-source-loading')).toBeNull();
    });
    expect(screen.getByText('First paragraph.')).toBeTruthy();
    expect(screen.getByText('Second paragraph.')).toBeTruthy();
  });

  it('re-fetches when retargeted to a new chapterId via onDidParametersChange', async () => {
    getOriginalContent.mockResolvedValueOnce('Chapter one text.');
    const props = dockProps({ bookId: 'b1', chapterId: 'c1' });
    render(<OriginalSourcePanel {...props} />);

    await waitFor(() => expect(screen.getByText('Chapter one text.')).toBeTruthy());
    expect(getOriginalContent).toHaveBeenCalledTimes(1);

    getOriginalContent.mockResolvedValueOnce('Chapter two text.');
    (props.api as unknown as { updateParameters: (n: Record<string, unknown>) => void })
      .updateParameters({ bookId: 'b1', chapterId: 'c2' });

    await waitFor(() => expect(screen.getByText('Chapter two text.')).toBeTruthy());
    expect(getOriginalContent).toHaveBeenCalledTimes(2);
    expect(getOriginalContent).toHaveBeenLastCalledWith('tok', 'b1', 'c2');
  });

  it('sets the dock tab title with a chapter suffix', () => {
    const props = dockProps({ bookId: 'b1', chapterId: '0199aabbccdd' });
    getOriginalContent.mockReturnValue(new Promise(() => {}));
    render(<OriginalSourcePanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalledWith('Original Source · 0199aabb');
  });
});
