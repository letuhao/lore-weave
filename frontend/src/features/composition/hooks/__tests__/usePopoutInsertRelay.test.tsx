import { renderHook, waitFor } from '@testing-library/react';
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

  // #16 2.8 /review-impl HIGH fix — a message with a `reqId` gets an ack reflecting whether
  // `onInsert` actually succeeded, so the popout's ProposeEditCard can tell a real success
  // apart from a silently-dropped relay.
  it('acks a reqId-tagged insert with ok=true when onInsert succeeds', async () => {
    const onInsert = vi.fn(() => true);
    renderHook(() => usePopoutInsertRelay('bk4', 'c1', onInsert));
    const popout = openPopoutChannel('bk4', 'c1');
    const acks: unknown[] = [];
    popout.subscribe((m) => { if (m.kind === 'insert-ack') acks.push(m); });
    // Two sequential BroadcastChannel hops (insert-prose to the hook, then its ack reply back)
    // — a single setTimeout(0) tick isn't reliably enough, poll instead.
    act(() => { popout.post({ kind: 'insert-prose', text: 'x', reqId: 'req-1' }); });
    await waitFor(() => expect(acks).toContainEqual({ kind: 'insert-ack', reqId: 'req-1', ok: true }));
    popout.close();
  });

  it('acks ok=false when onInsert returns false (e.g. no live editor)', async () => {
    const onInsert = vi.fn(() => false);
    renderHook(() => usePopoutInsertRelay('bk5', 'c1', onInsert));
    const popout = openPopoutChannel('bk5', 'c1');
    const acks: unknown[] = [];
    popout.subscribe((m) => { if (m.kind === 'insert-ack') acks.push(m); });
    act(() => { popout.post({ kind: 'insert-prose', text: 'x', reqId: 'req-2' }); });
    await waitFor(() => expect(acks).toContainEqual({ kind: 'insert-ack', reqId: 'req-2', ok: false }));
    popout.close();
  });

  it('sends no ack when the message has no reqId (legacy PopoutHost sender, unchanged)', async () => {
    const onInsert = vi.fn(() => true);
    renderHook(() => usePopoutInsertRelay('bk6', 'c1', onInsert));
    const popout = openPopoutChannel('bk6', 'c1');
    const acks: unknown[] = [];
    popout.subscribe((m) => { if (m.kind === 'insert-ack') acks.push(m); });
    await act(async () => {
      popout.post({ kind: 'insert-prose', text: 'x' });
      // No reqId ⇒ no ack is ever sent; wait out a settle window instead of polling for one.
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(onInsert).toHaveBeenCalled();
    expect(acks).toHaveLength(0);
    popout.close();
  });
});
