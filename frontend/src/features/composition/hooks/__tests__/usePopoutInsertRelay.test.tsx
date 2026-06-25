import { renderHook } from '@testing-library/react';
import { act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { usePopoutInsertRelay } from '../usePopoutInsertRelay';
import { openPopoutChannel } from '../../workspace/popoutChannel';

describe('usePopoutInsertRelay (T5.4 M4)', () => {
  it('forwards a popout insert-prose to the opener editor handler', async () => {
    const onInsert = vi.fn();
    renderHook(() => usePopoutInsertRelay('bk', 'c1', onInsert));
    const popout = openPopoutChannel('bk', 'c1');
    await act(async () => {
      popout.post({ kind: 'insert-prose', text: 'drafted in window 2', model: 'qwen' });
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(onInsert).toHaveBeenCalledWith('drafted in window 2', 'qwen');
    popout.close();
  });

  it('ignores non-insert messages (e.g. dock-back)', async () => {
    const onInsert = vi.fn();
    renderHook(() => usePopoutInsertRelay('bk2', 'c1', onInsert));
    const popout = openPopoutChannel('bk2', 'c1');
    await act(async () => {
      popout.post({ kind: 'dock-back', panel: 'compose' });
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(onInsert).not.toHaveBeenCalled();
    popout.close();
  });

  it('unsubscribes on unmount (no stale insert after the editor is gone)', async () => {
    const onInsert = vi.fn();
    const { unmount } = renderHook(() => usePopoutInsertRelay('bk3', 'c1', onInsert));
    unmount();
    const popout = openPopoutChannel('bk3', 'c1');
    await act(async () => {
      popout.post({ kind: 'insert-prose', text: 'late', model: undefined });
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(onInsert).not.toHaveBeenCalled();
    popout.close();
  });
});
