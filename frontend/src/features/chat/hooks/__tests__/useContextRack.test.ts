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

  describe('pinnedLegacyTools (CAT-4 Part D)', () => {
    it('unions a pin into pinned_legacy_tools via a SEPARATE PATCH from enabled_tools', () => {
      const onSessionUpdate = vi.fn();
      const { result } = renderHook(() =>
        useContextRack({
          session: { ...baseSession, enabled_tools: [], enabled_skills: [], pinned_legacy_tools: [] },
          accessToken: 'tok',
          onSessionUpdate,
        }),
      );

      act(() => {
        result.current.addPinnedLegacyTool('glossary_book_create');
      });
      expect(onSessionUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ pinned_legacy_tools: ['glossary_book_create'] }),
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(patchSessionMock).toHaveBeenCalledWith('tok', 's1', {
        pinned_legacy_tools: ['glossary_book_create'],
      });
      // Must never bundle into the SAME patch as enabled_tools — a pin must not
      // ride along with (or be mistaken for) a curated-mode enabled_tools write.
      expect(patchSessionMock).not.toHaveBeenCalledWith(
        'tok', 's1', expect.objectContaining({ enabled_tools: expect.anything() }),
      );
    });

    it('removePinnedLegacyTool drops the name and re-PATCHes', () => {
      const onSessionUpdate = vi.fn();
      const { result } = renderHook(() =>
        useContextRack({
          session: { ...baseSession, pinned_legacy_tools: ['glossary_book_create', 'glossary_user_delete'] },
          accessToken: 'tok',
          onSessionUpdate,
        }),
      );

      act(() => {
        result.current.removePinnedLegacyTool('glossary_book_create');
      });
      expect(onSessionUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ pinned_legacy_tools: ['glossary_user_delete'] }),
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(patchSessionMock).toHaveBeenCalledWith('tok', 's1', {
        pinned_legacy_tools: ['glossary_user_delete'],
      });
    });

    it('warns and refuses past the pin limit', () => {
      const session = {
        ...baseSession,
        pinned_legacy_tools: Array.from({ length: 16 }, (_, i) => `legacy_${i}`),
      } as ChatSession;
      const onSessionUpdate = vi.fn();
      const { result } = renderHook(() =>
        useContextRack({ session, accessToken: 'tok', onSessionUpdate }),
      );

      act(() => {
        result.current.addPinnedLegacyTool('one_too_many');
      });

      expect(toast.warning).toHaveBeenCalled();
      expect(onSessionUpdate).not.toHaveBeenCalled();
      expect(patchSessionMock).not.toHaveBeenCalled();
    });
  });
});
