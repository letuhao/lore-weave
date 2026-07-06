// #16 Phase 2 (2.7) — MediaVersionHistoryPanel: a per-resource retargeting dock panel (J1/R3
// precedent, same shape as JsonEditorPanel) that renders the existing VersionHistoryPanel AS-IS
// (DOCK-2) with params read from props.params, self-titles, and retargets on
// onDidParametersChange (re-opening a different block must land the new target, not the stale
// one from first mount).
import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));

const versionHistoryPanelSpy = vi.fn();
vi.mock('@/components/editor/VersionHistoryPanel', () => ({
  VersionHistoryPanel: (props: any) => {
    versionHistoryPanelSpy(props);
    return <div data-testid="version-history-stub" />;
  },
}));

import { MediaVersionHistoryPanel } from '../MediaVersionHistoryPanel';

function dockProps(params?: Record<string, unknown>) {
  let paramsListener: ((next: Record<string, unknown> | undefined) => void) | null = null;
  const api = {
    setTitle: vi.fn(),
    close: vi.fn(),
    onDidParametersChange: (cb: (next: Record<string, unknown> | undefined) => void) => {
      paramsListener = cb;
      return { dispose: vi.fn() };
    },
  };
  return {
    props: { api, params } as unknown as IDockviewPanelProps,
    api,
    fireParamsChange: (next: Record<string, unknown> | undefined) => paramsListener?.(next),
  };
}

describe('MediaVersionHistoryPanel', () => {
  it('mounts VersionHistoryPanel with token + params mapped 1:1', () => {
    const { props } = dockProps({
      bookId: 'b1', chapterId: 'c1', blockId: 'blk1',
      blockTitle: 'cover.png', currentMediaUrl: 'https://example.com/cover.png',
    });
    render(<MediaVersionHistoryPanel {...props} />);

    expect(screen.getByTestId('version-history-stub')).toBeTruthy();
    expect(versionHistoryPanelSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        token: 'tok-1',
        bookId: 'b1',
        chapterId: 'c1',
        blockId: 'blk1',
        blockTitle: 'cover.png',
        currentMediaUrl: 'https://example.com/cover.png',
      }),
    );
  });

  it('self-titles with the block title', () => {
    const { props } = dockProps({ bookId: 'b1', chapterId: 'c1', blockId: 'blk1', blockTitle: 'cover.png' });
    render(<MediaVersionHistoryPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalledWith('Version History · cover.png');
  });

  it('onClose calls props.api.close()', () => {
    const { props, api } = dockProps({ bookId: 'b1', chapterId: 'c1', blockId: 'blk1', blockTitle: 't' });
    render(<MediaVersionHistoryPanel {...props} />);
    const passed = versionHistoryPanelSpy.mock.calls.at(-1)![0];
    passed.onClose();
    expect(api.close).toHaveBeenCalled();
  });

  it('renders the empty-state hint when no target params are given', () => {
    const { props } = dockProps();
    render(<MediaVersionHistoryPanel {...props} />);
    expect(screen.getByTestId('studio-media-version-history').textContent).toContain('No media block selected.');
    expect(screen.queryByTestId('version-history-stub')).toBeNull();
  });

  it('retargets on onDidParametersChange (re-opening a different block updates props)', () => {
    const { props, fireParamsChange } = dockProps({
      bookId: 'b1', chapterId: 'c1', blockId: 'blk1', blockTitle: 'first.png',
    });
    render(<MediaVersionHistoryPanel {...props} />);
    expect(versionHistoryPanelSpy.mock.calls.at(-1)![0].blockId).toBe('blk1');

    act(() => {
      fireParamsChange({ bookId: 'b1', chapterId: 'c1', blockId: 'blk2', blockTitle: 'second.png' });
    });

    expect(versionHistoryPanelSpy.mock.calls.at(-1)![0].blockId).toBe('blk2');
    expect(props.api.setTitle).toHaveBeenLastCalledWith('Version History · second.png');
  });
});
