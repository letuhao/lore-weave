import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { toast } from 'sonner';
import { useContextRack } from '../useContextRack';
import type { ChatSession } from '../../types';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), warning: vi.fn() } }));

const patchSessionMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    patchSession: (...args: unknown[]) => patchSessionMock(...args),
  },
}));

const baseSession = {
  session_id: 's1',
  owner_user_id: 'u1',
  title: 't',
  model_source: 'user_model',
  model_ref: 'm1',
  status: 'active',
} as unknown as ChatSession;

describe('useContextRack', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    patchSessionMock.mockReset();
    patchSessionMock.mockResolvedValue(baseSession);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('updates streamPinsRef synchronously before PATCH debounce', () => {
    const onSessionUpdate = vi.fn();
    const { result } = renderHook(() =>
      useContextRack({
        session: { ...baseSession, enabled_tools: [], enabled_skills: [] },
        accessToken: 'tok',
        onSessionUpdate,
      }),
    );

    act(() => {
      result.current.addTool('find_tools');
    });

    expect(result.current.streamPinsRef.current.enabledTools).toEqual(['find_tools']);
    expect(patchSessionMock).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(patchSessionMock).toHaveBeenCalledWith('tok', 's1', { enabled_tools: ['find_tools'] });
  });

  it('warns on tool soft limit but still adds', () => {
    let session = { ...baseSession, enabled_tools: Array.from({ length: 8 }, (_, i) => `tool_${i}`), enabled_skills: [] } as ChatSession;
    const onSessionUpdate = vi.fn((s: ChatSession) => { session = s; });
    const { result, rerender } = renderHook(() =>
      useContextRack({
        session,
        accessToken: 'tok',
        onSessionUpdate,
      }),
    );

    act(() => {
      result.current.addTool('tool_extra');
    });
    rerender();

    expect(toast.warning).toHaveBeenCalled();
    expect(result.current.enabledTools).toHaveLength(9);
  });
});
