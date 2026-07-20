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

  // Phase 4 (P4.1) — the studio dock-nav tools come back as an io.loreweave/ui-directive
  // RESULT now (ai-gateway consumer-local), NOT a suspend. The executor runs the host effect
  // directly; there is no resolve to submit. (The result carries chat-service's real
  // {ok, result: <directive>} envelope.)
  const studioDirective = (tool: string, args: Record<string, unknown>, id: string) => ({
    tool, ok: true, pending: false, toolCallId: id,
    result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool, args } },
  });

  it('runs a studio ui directive against the host (idempotent, no resolve)', () => {
    stream.value = {
      messages: [{ message_id: 'm1', tool_calls: [studioDirective('ui_open_studio_panel', { panel_id: 'cast' }, 't1')] }],
    };
    const { rerender } = renderHook(() => useStudioUiToolExecutor());
    expect(host.value.openPanel).toHaveBeenCalledWith('cast');
    (host.value.openPanel as ReturnType<typeof vi.fn>).mockClear();
    rerender(); // same directive must not fire twice
    expect(host.value.openPanel).not.toHaveBeenCalled();
  });

  it('focuses a manuscript unit for ui_focus_manuscript_unit', () => {
    stream.value = {
      messages: [{ message_id: 'm1', tool_calls: [studioDirective('ui_focus_manuscript_unit', { chapter_id: 'ch9' }, 't2')] }],
    };
    renderHook(() => useStudioUiToolExecutor());
    expect(host.value.focusManuscriptUnit).toHaveBeenCalledWith('ch9');
  });

  it('ignores the chat own ui_* tools (disjoint from the studio set)', () => {
    stream.value = {
      messages: [{ message_id: 'm1', tool_calls: [studioDirective('ui_navigate', { path: '/books' }, 't1')] }],
    };
    renderHook(() => useStudioUiToolExecutor());
    // the chat's own executor handles ui_navigate; the studio hook must not touch the host
    expect(host.value.openPanel).not.toHaveBeenCalled();
    expect(host.value.focusManuscriptUnit).not.toHaveBeenCalled();
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
