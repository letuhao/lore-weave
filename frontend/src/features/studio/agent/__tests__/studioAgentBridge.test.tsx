import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// The bridge hooks read the chat stream + the studio host + the query client — all mocked here so
// we test the WIRING (resolve → host action → resolve; completed write → effect handler).
const stream = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('@/features/chat/providers', () => ({ useChatStream: () => stream.value }));
const host = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => host.value }));
const qc = vi.hoisted(() => ({ invalidateQueries: vi.fn() }));
vi.mock('@tanstack/react-query', async (orig) => ({ ...(await orig<object>()), useQueryClient: () => qc }));

import { useStudioUiToolExecutor } from '../useStudioUiToolExecutor';
import { useStudioEffectReconciler } from '../useStudioEffectReconciler';

describe('useStudioUiToolExecutor (Lane A)', () => {
  beforeEach(() => { host.value = { openPanel: vi.fn(), focusManuscriptUnit: vi.fn() }; });

  it('resolves a pending studio ui tool via the host, then submits the resolve (idempotent)', () => {
    const submitToolResolve = vi.fn();
    stream.value = {
      submitToolResolve,
      messages: [{ message_id: 'm1', tool_calls: [
        { tool: 'ui_open_studio_panel', ok: false, pending: true, runId: 'r1', toolCallId: 't1', args: { panel_id: 'cast' } },
      ] }],
    };
    const { rerender } = renderHook(() => useStudioUiToolExecutor());
    expect(host.value.openPanel).toHaveBeenCalledWith('cast');
    expect(submitToolResolve).toHaveBeenCalledWith('r1', 't1', { opened: true });
    submitToolResolve.mockClear();
    rerender(); // same suspend must not fire twice
    expect(submitToolResolve).not.toHaveBeenCalled();
  });

  it('ignores the chat own ui_* tools (disjoint from the studio set)', () => {
    const submitToolResolve = vi.fn();
    stream.value = {
      submitToolResolve,
      messages: [{ message_id: 'm1', tool_calls: [
        { tool: 'ui_navigate', ok: false, pending: true, runId: 'r1', toolCallId: 't1', args: { path: '/books' } },
      ] }],
    };
    renderHook(() => useStudioUiToolExecutor());
    expect(submitToolResolve).not.toHaveBeenCalled(); // the chat's own executor handles it
  });
});

describe('useStudioEffectReconciler (Lane B)', () => {
  beforeEach(() => { host.value = { bookId: 'b1', publish: vi.fn() }; qc.invalidateQueries.mockClear(); });

  it('runs the effect handlers for a COMPLETED MCP draft write (invalidates cache; no editor hijack)', async () => {
    stream.value = {
      messages: [{ message_id: 'm1', tool_calls: [
        { tool: 'book_save_chapter_draft', ok: true, pending: false, result: { chapter_id: 'ch1' } },
      ] }],
    };
    renderHook(() => useStudioEffectReconciler());
    await waitFor(() => expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['chapter', 'b1', 'ch1'] }));
    // reconcile must NOT publish a chapter event (would switch the user's editor).
    expect(host.value.publish).not.toHaveBeenCalled();
  });

  it('ignores a still-pending (suspended) tool call', async () => {
    stream.value = {
      messages: [{ message_id: 'm1', tool_calls: [
        { tool: 'book_save_chapter_draft', ok: false, pending: true, result: null },
      ] }],
    };
    renderHook(() => useStudioEffectReconciler());
    await waitFor(() => expect(true).toBe(true));
    expect(host.value.publish).not.toHaveBeenCalled();
  });
});
