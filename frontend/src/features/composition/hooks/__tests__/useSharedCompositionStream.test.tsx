import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSharedCompositionStream } from '../useSharedCompositionStream';
import type { LiveStreamState } from '../../workers/liveStateHub';

type FakePort = { postMessage: ReturnType<typeof vi.fn>; onmessage: ((e: { data: unknown }) => void) | null; onmessageerror: (() => void) | null; start: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> };
let lastPort: FakePort;
let lastWorker: FakeSharedWorker;

class FakeSharedWorker {
  port: FakePort;
  onerror: (() => void) | null = null;
  constructor() {
    this.port = { postMessage: vi.fn(), onmessage: null, onmessageerror: null, start: vi.fn(), close: vi.fn() };
    lastPort = this.port;
    lastWorker = this;
  }
}

beforeEach(() => vi.stubGlobal('SharedWorker', FakeSharedWorker));
afterEach(() => vi.unstubAllGlobals());

const snap = (over: Partial<LiveStreamState> = {}): LiveStreamState =>
  ({ ghost: '', streaming: false, jobId: null, error: null, reasoning: null, ...over });

const ARGS = { projectId: 'p1', modelSource: 'user_model', modelRef: 'm1' };

describe('useSharedCompositionStream (T5.4 M4 Slice B)', () => {
  it('does NOT create a worker when disabled (caller uses the in-process path)', () => {
    renderHook(() => useSharedCompositionStream('tok', false));
    // lastPort would be set by a constructed FakeSharedWorker; none should be made
    expect(lastPort).toBeUndefined();
  });

  it('connects + starts the port when enabled and mirrors broadcast snapshots', () => {
    const { result } = renderHook(() => useSharedCompositionStream('tok', true));
    expect(lastPort.start).toHaveBeenCalledTimes(1);
    act(() => lastPort.onmessage!({ data: { type: 'state', state: snap({ ghost: 'Hello', streaming: true, jobId: 'j1' }) } }));
    expect(result.current.ghost).toBe('Hello');
    expect(result.current.streaming).toBe(true);
    expect(result.current.jobId).toBe('j1');
  });

  it('start() posts a start command WITH the latest token', async () => {
    const { result, rerender } = renderHook(({ t }) => useSharedCompositionStream(t, true), { initialProps: { t: 'tok1' } });
    rerender({ t: 'tok2' });   // token rotated — start must use the latest
    await act(async () => { await result.current.start(ARGS); });
    expect(lastPort.postMessage).toHaveBeenCalledWith({ type: 'start', args: ARGS, token: 'tok2' });
  });

  it('stop() and clearGhost() post their commands; clear is locally optimistic', () => {
    const { result } = renderHook(() => useSharedCompositionStream('tok', true));
    act(() => lastPort.onmessage!({ data: { type: 'state', state: snap({ ghost: 'text' }) } }));
    act(() => result.current.stop());
    expect(lastPort.postMessage).toHaveBeenCalledWith({ type: 'stop' });
    act(() => result.current.clearGhost());
    expect(lastPort.postMessage).toHaveBeenCalledWith({ type: 'clear' });
    expect(result.current.ghost).toBe('');   // optimistic local clear
  });

  it('closes its port on unmount (window navigating away)', () => {
    const { unmount } = renderHook(() => useSharedCompositionStream('tok', true));
    const port = lastPort;
    unmount();
    expect(port.close).toHaveBeenCalledTimes(1);
  });

  it('surfaces a worker error instead of hanging silently (/review-impl MED)', () => {
    const { result } = renderHook(() => useSharedCompositionStream('tok', true));
    expect(result.current.error).toBeNull();
    act(() => lastWorker.onerror!());
    expect(result.current.error).toMatch(/worker failed/i);
    expect(result.current.streaming).toBe(false);
  });
});
