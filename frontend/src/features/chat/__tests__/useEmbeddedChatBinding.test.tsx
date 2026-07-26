import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import type { ChatSession } from '../types';

// ARCH-1 C5 — the editor AI panel binding logic: resolve the book's project,
// select/bind a book-scoped session.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

vi.mock('sonner', () => ({ toast: { warning: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const listProjectsMock = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: {
    listProjects: (...a: unknown[]) => listProjectsMock(...a),
  },
}));

const patchSessionMock = vi.fn();
const listSessionsMock = vi.fn();
vi.mock('../api', () => ({
  chatApi: {
    patchSession: (...a: unknown[]) => patchSessionMock(...a),
    listSessions: (...a: unknown[]) => listSessionsMock(...a),
  },
}));

import { useEmbeddedChatBinding } from '../useEmbeddedChatBinding';

function makeSession(over: Partial<ChatSession> = {}): ChatSession {
  return {
    session_id: 's-1',
    title: 'T',
    project_id: null,
    model_ref: 'm',
    model_source: 'user_model',
    status: 'active',
    created_at: '',
    updated_at: '',
    message_count: 0,
    ...(over as ChatSession),
  } as ChatSession;
}

function deps(over: Partial<Parameters<typeof useEmbeddedChatBinding>[0]> = {}) {
  return {
    bookId: 'book-1',
    sessions: [] as ChatSession[],
    sessionsLoading: false,
    activeSession: null as ChatSession | null,
    selectSession: vi.fn(),
    updateActiveSession: vi.fn(),
    ...over,
  };
}

describe('useEmbeddedChatBinding', () => {
  beforeEach(() => {
    listProjectsMock.mockReset();
    patchSessionMock.mockReset();
    listSessionsMock.mockReset();
    // Default: no book-scoped session exists server-side either (the direct
    // fallback fetch, D-COMPOSE-SESSION-RESTORE, finds nothing) — tests that
    // want to exercise the fallback finding a session override this.
    listSessionsMock.mockResolvedValue({ items: [], next_cursor: null });
  });

  it('resolves the book project and selects an existing book-scoped session', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    const bound = makeSession({ session_id: 's-bound', project_id: 'proj-9' });
    const d = deps({ sessions: [bound] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(d.selectSession).toHaveBeenCalledWith(bound));
    expect(result.current.projectId).toBe('proj-9');
    expect(result.current.needsNewSession).toBe(false);
    // listProjects filtered by the book
    expect(listProjectsMock).toHaveBeenCalledWith(
      expect.objectContaining({ book_id: 'book-1' }),
      'tok-test',
    );
  });

  it('signals needsNewSession when the book has a project but no session yet', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    const d = deps({ sessions: [] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(result.current.needsNewSession).toBe(true));
    expect(d.selectSession).not.toHaveBeenCalled();
  });

  it('D-COMPOSE-SESSION-RESTORE: falls back to a direct book_id fetch when a fresh 0-message session sorted outside the loaded list', async () => {
    // The bug: a brand-new session has last_message_at=null, sorts LAST by
    // the list endpoint's ORDER BY ... NULLS LAST, and can fall outside the
    // already-loaded `sessions` page — the same class of bug as
    // D-CHAT-URL-SESSION-ACTIVATION. The local `sessions` array (as loaded
    // generically, unfiltered by book) has nothing for this book; the direct
    // book_id-scoped fetch is what actually finds it.
    listProjectsMock.mockResolvedValue({ items: [] });
    const freshSession = makeSession({ session_id: 's-fresh', book_id: 'book-1', last_message_at: null });
    listSessionsMock.mockResolvedValue({ items: [freshSession], next_cursor: null });
    const d = deps({ sessions: [] }); // not in the generically-loaded list

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(d.selectSession).toHaveBeenCalledWith(freshSession));
    expect(result.current.needsNewSession).toBe(false);
    expect(listSessionsMock).toHaveBeenCalledWith('tok-test', 'active', 'book-1');
  });

  it('signals needsNewSession when the direct book_id fetch also finds nothing', async () => {
    listProjectsMock.mockResolvedValue({ items: [] });
    listSessionsMock.mockResolvedValue({ items: [], next_cursor: null });
    const d = deps({ sessions: [] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(result.current.needsNewSession).toBe(true));
    expect(d.selectSession).not.toHaveBeenCalled();
  });

  it('degrades to needsNewSession when the direct book_id fetch fails', async () => {
    listProjectsMock.mockResolvedValue({ items: [] });
    listSessionsMock.mockRejectedValue(new Error('down'));
    const d = deps({ sessions: [] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(result.current.needsNewSession).toBe(true));
    expect(d.selectSession).not.toHaveBeenCalled();
  });

  it('binds a newly-active unbound session to the book project via patchSession', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    patchSessionMock.mockResolvedValue(makeSession({ session_id: 's-new', project_id: 'proj-9' }));
    // session is active but not yet bound to the project
    const active = makeSession({ session_id: 's-new', project_id: null });
    const d = deps({ activeSession: active });

    renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() =>
      expect(patchSessionMock).toHaveBeenCalledWith('tok-test', 's-new', { project_id: 'proj-9' }),
    );
    await waitFor(() => expect(d.updateActiveSession).toHaveBeenCalled());
  });

  it('does NOT re-patch a session already bound to the project', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    const active = makeSession({ project_id: 'proj-9' });
    const d = deps({ activeSession: active });

    renderHook(() => useEmbeddedChatBinding(d));

    // give effects a tick
    await waitFor(() => expect(listProjectsMock).toHaveBeenCalled());
    expect(patchSessionMock).not.toHaveBeenCalled();
  });

  it('degrades to no-project (null) when the book has no knowledge project', async () => {
    listProjectsMock.mockResolvedValue({ items: [] });
    const d = deps({ sessions: [] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(result.current.projectId).toBeNull());
    // no project → no patch, and no book-scoped session to select
    expect(patchSessionMock).not.toHaveBeenCalled();
  });

  it('degrades to no-project when listProjects fails', async () => {
    listProjectsMock.mockRejectedValue(new Error('down'));
    const d = deps();

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(result.current.projectId).toBeNull());
  });

  it('treats a missing bookId as no-project (no API call)', async () => {
    const d = deps({ bookId: undefined });
    const { result } = renderHook(() => useEmbeddedChatBinding(d));
    await waitFor(() => expect(result.current.projectId).toBeNull());
    expect(listProjectsMock).not.toHaveBeenCalled();
  });

  it('re-resolves the project when bookId changes (cross-book regression)', async () => {
    // review-impl C5 #1: in production <Chat key={bookId}> forces a full
    // remount per book so a fresh hook resolves the new book. This asserts the
    // resolve effect itself reacts to bookId (the API is re-queried for book B),
    // guarding against the resolve step silently caching book A's project.
    listProjectsMock.mockImplementation((params: { book_id?: string }) =>
      Promise.resolve({
        items: params.book_id === 'book-A' ? [{ project_id: 'proj-A' }] : [{ project_id: 'proj-B' }],
      }),
    );
    const d = deps({ bookId: 'book-A' });
    const { result, rerender } = renderHook((p: typeof d) => useEmbeddedChatBinding(p), {
      initialProps: d,
    });
    await waitFor(() => expect(result.current.projectId).toBe('proj-A'));

    rerender({ ...d, bookId: 'book-B' });
    await waitFor(() => expect(result.current.projectId).toBe('proj-B'));
    expect(listProjectsMock).toHaveBeenCalledWith(
      expect.objectContaining({ book_id: 'book-B' }),
      'tok-test',
    );
  });

  it('D-COMPOSE-SESSION-RESTORE: restores the last session by book_id even when the book has NO knowledge project', async () => {
    // The bug: projectId is null forever for a book with no KG project, so
    // the OLD `projectId ? sessions.find(...) : undefined` logic could never
    // find a session for such a book — every reopen forced a new chat.
    listProjectsMock.mockResolvedValue({ items: [] });
    const mine = makeSession({ session_id: 's-mine', book_id: 'book-1', project_id: null });
    const otherBook = makeSession({ session_id: 's-other', book_id: 'book-2', project_id: null });
    const d = deps({ sessions: [mine, otherBook] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(d.selectSession).toHaveBeenCalledWith(mine));
    expect(result.current.needsNewSession).toBe(false);
  });

  it('prefers a book_id match over a project_id match when both are present', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    const byBookId = makeSession({ session_id: 's-by-book', book_id: 'book-1', project_id: null });
    const byProjectId = makeSession({ session_id: 's-by-project', book_id: null, project_id: 'proj-9' });
    const d = deps({ sessions: [byBookId, byProjectId] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(d.selectSession).toHaveBeenCalledWith(byBookId));
    expect(result.current.needsNewSession).toBe(false);
  });

  it('falls back to a project_id match for a legacy session never tagged with book_id', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    const legacy = makeSession({ session_id: 's-legacy', book_id: null, project_id: 'proj-9' });
    const d = deps({ sessions: [legacy] });

    const { result } = renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(d.selectSession).toHaveBeenCalledWith(legacy));
    expect(result.current.needsNewSession).toBe(false);
  });

  it('does not throw when the project-bind patch fails (graceful degrade)', async () => {
    listProjectsMock.mockResolvedValue({ items: [{ project_id: 'proj-9' }] });
    patchSessionMock.mockRejectedValue(new Error('patch down'));
    const active = makeSession({ session_id: 's-x', project_id: null });
    const d = deps({ activeSession: active });

    renderHook(() => useEmbeddedChatBinding(d));

    await waitFor(() => expect(patchSessionMock).toHaveBeenCalled());
    // failure is swallowed (toast warned) — updateActiveSession never called,
    // no unhandled rejection.
    expect(d.updateActiveSession).not.toHaveBeenCalled();
  });
});
