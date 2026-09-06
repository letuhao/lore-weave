import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// D-PROPOSE-EDIT-ACTS-ON-EDITOR-STATE-THE-TURN-CANNOT-SEE. propose_edit's replace_selection
// presupposes a selection the turn never carried, so a model asked to rewrite a passage could
// not tell whether calling it was grounded in anything the author actually selected. This adds a
// live snapshot, taken at SEND TIME (mirroring ProposeEditCard's own read of the same handle),
// rather than a continuously-synced prop — which would re-render the chat subtree on every
// selection change.

let selection: { from: number; to: number; empty: boolean; text: string } | null = null;
let noEditorTarget = false;

vi.mock('../../context/editorBridge', () => ({
  getEditorTarget: () => (noEditorTarget ? null : { handle: { getSelection: () => selection } }),
}));

import { withSelectionSnapshot } from '../useChatMessages';

describe('withSelectionSnapshot (pure)', () => {
  beforeEach(() => {
    selection = null;
    noEditorTarget = false;
  });

  it('passes editorContext through unchanged when nothing is registered', () => {
    expect(withSelectionSnapshot(undefined)).toBeUndefined();
  });

  it('omits selection fields (does not guess) when no editor is mounted', () => {
    noEditorTarget = true;
    const ctx = { book_id: 'b1', chapter_id: 'c1' };
    expect(withSelectionSnapshot(ctx)).toEqual(ctx);
  });

  it('reports has_selection=false and no selected_text for an empty selection', () => {
    selection = { from: 5, to: 5, empty: true, text: '' };
    const out = withSelectionSnapshot({ book_id: 'b1', chapter_id: 'c1' });
    expect(out).toEqual({ book_id: 'b1', chapter_id: 'c1', has_selection: false });
    expect(out).not.toHaveProperty('selected_text');
  });

  it('reports has_selection=true and the selected text for a real selection', () => {
    selection = { from: 5, to: 20, empty: false, text: 'the opening line' };
    const out = withSelectionSnapshot({ book_id: 'b1', chapter_id: 'c1' });
    expect(out).toEqual({
      book_id: 'b1', chapter_id: 'c1', has_selection: true, selected_text: 'the opening line',
    });
  });

  it('truncates a long selection to a preview rather than echoing the whole span', () => {
    selection = { from: 0, to: 5000, empty: false, text: 'x'.repeat(5000) };
    const out = withSelectionSnapshot({ book_id: 'b1', chapter_id: 'c1' });
    expect(out?.selected_text?.length).toBe(200);
  });
});

// ── the real call site: does the snapshot reach the POST body? ────────────────────────────────

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-test' }) }));
vi.mock('../../api', () => ({
  chatApi: {
    listMessages: vi.fn().mockResolvedValue({ items: [] }),
    getLatestContextBudget: () => Promise.resolve({ budget: null }),
    messagesUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/messages`,
  },
}));

import { useChatMessages } from '../useChatMessages';

function sseResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(`data: ${line}\n`));
      controller.close();
    },
  });
  return { ok: true, status: 200, statusText: 'OK', body } as unknown as Response;
}

function stubFetch(lines: string[]) {
  const fetchMock = vi.fn().mockResolvedValue(sseResponse(lines));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('useChatMessages send() — the selection snapshot reaches editor_context', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends has_selection + selected_text when the editor has a real selection', async () => {
    selection = { from: 5, to: 20, empty: false, text: 'the opening line' };
    const fetchMock = stubFetch([
      JSON.stringify({ type: 'RUN_FINISHED' }),
    ]);
    const { result } = renderHook(() =>
      useChatMessages('s-1', { book_id: 'b1', chapter_id: 'c1' }, undefined, undefined, undefined, [], []),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('make this darker');
    });
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    expect(body.editor_context).toEqual({
      book_id: 'b1', chapter_id: 'c1', has_selection: true, selected_text: 'the opening line',
    });
  });

  it('sends has_selection=false and no selected_text when nothing is selected', async () => {
    selection = { from: 5, to: 5, empty: true, text: '' };
    const fetchMock = stubFetch([
      JSON.stringify({ type: 'RUN_FINISHED' }),
    ]);
    const { result } = renderHook(() =>
      useChatMessages('s-1', { book_id: 'b1', chapter_id: 'c1' }, undefined, undefined, undefined, [], []),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('make this darker');
    });
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    expect(body.editor_context).toEqual({ book_id: 'b1', chapter_id: 'c1', has_selection: false });
    expect(body.editor_context).not.toHaveProperty('selected_text');
  });
});
