// F-QC-1 — the diary assistant auto-creates its session with the default model (no generic new-chat dialog).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const get = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/settings/api', () => ({
  CHAT_CAPABILITY: 'chat',
  defaultModelsApi: { get: (...a: unknown[]) => get(...a) },
}));

import { useAssistantAutoSession } from '../useAssistantAutoSession';

beforeEach(() => get.mockReset());

describe('useAssistantAutoSession (F-QC-1)', () => {
  it('auto-creates an assistant session with the default chat model + suppresses the generic dialog', async () => {
    get.mockResolvedValueOnce({ defaults: { chat: 'model-abc' } });
    const createSession = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      useAssistantAutoSession({ enabled: true, needsNewSession: true, hasActiveSession: false, bookId: 'book-1', createSession }),
    );
    // Suppresses immediately (the assistant owns the create — no flash of the generic dialog).
    expect(result.current.suppressGenericDialog).toBe(true);
    await waitFor(() =>
      expect(createSession).toHaveBeenCalledWith({
        model_source: 'user_model',
        model_ref: 'model-abc',
        title: 'Work Assistant',
        book_id: 'book-1',
        session_kind: 'assistant',
      }),
    );
  });

  it('falls back to the manual dialog when there is NO default model (never a dead surface)', async () => {
    get.mockResolvedValueOnce({ defaults: {} });
    const createSession = vi.fn();
    const { result } = renderHook(() =>
      useAssistantAutoSession({ enabled: true, needsNewSession: true, hasActiveSession: false, bookId: 'book-1', createSession }),
    );
    await waitFor(() => expect(result.current.suppressGenericDialog).toBe(false)); // released → dialog shows
    expect(createSession).not.toHaveBeenCalled();
  });

  it('does nothing for a normal chat (not the assistant)', async () => {
    const createSession = vi.fn();
    const { result } = renderHook(() =>
      useAssistantAutoSession({ enabled: false, needsNewSession: true, hasActiveSession: false, bookId: 'book-1', createSession }),
    );
    expect(result.current.suppressGenericDialog).toBe(false);
    expect(get).not.toHaveBeenCalled();
    expect(createSession).not.toHaveBeenCalled();
  });

  it('does not create when a session is already active', async () => {
    const createSession = vi.fn();
    renderHook(() =>
      useAssistantAutoSession({ enabled: true, needsNewSession: false, hasActiveSession: true, bookId: 'book-1', createSession }),
    );
    expect(get).not.toHaveBeenCalled();
    expect(createSession).not.toHaveBeenCalled();
  });
});
