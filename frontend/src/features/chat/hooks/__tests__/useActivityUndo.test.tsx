import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

// MCP fan-out (C-ACTIVITY) — /review-impl FIX 2: the Undo issuer hardenings.
//   (a) the directive is STRUCTURED (a fenced {tool,args} JSON block), not raw
//       args spliced into prose;
//   (b) `undo.tool` is gated against ALLOWED_UNDO_TOOLS — a non-allowlisted tool
//       is never issued; `undo.available===false` also blocks.

const send = vi.fn().mockResolvedValue('');
vi.mock('../../providers', () => ({
  useChatStreamOptional: () => ({ send }),
}));

import {
  useActivityUndo,
  canUndo,
  buildUndoDirective,
  ALLOWED_UNDO_TOOLS,
} from '../useActivityUndo';
import type { ActivityEvent } from '../../types';

const allowed: ActivityEvent = {
  op: 'chapter.create',
  summary: "Created draft chapter 'Chapter 5'",
  undo: { available: true, tool: 'chapter_delete', args: { book_id: 'b1', chapter_id: 'ch5' } },
};

describe('useActivityUndo (FIX 2)', () => {
  beforeEach(() => send.mockClear());

  it('issues an allowlisted reverse tool as a STRUCTURED directive (no raw-args prose)', () => {
    const { result } = renderHook(() => useActivityUndo());
    void result.current(allowed);
    expect(send).toHaveBeenCalledTimes(1);
    const directive = send.mock.calls[0][0] as string;
    // structured: fenced undo-directive block carrying the exact {tool,args}.
    expect(directive).toContain('```undo-directive');
    expect(directive).toContain(JSON.stringify({ tool: 'chapter_delete', args: { book_id: 'b1', chapter_id: 'ch5' } }));
    // it must NOT interpolate raw args JSON loose in the prose sentence — the
    // only JSON.stringify of args lives inside the fenced block.
    const beforeFence = directive.split('```undo-directive')[0];
    expect(beforeFence).not.toContain('book_id');
  });

  it('does NOT issue a non-allowlisted reverse tool', () => {
    const { result } = renderHook(() => useActivityUndo());
    const evil: ActivityEvent = {
      op: 'x.y',
      summary: 'sketchy op',
      undo: { available: true, tool: 'rm_rf_everything', args: { all: true } },
    };
    expect(canUndo(evil)).toBe(false);
    expect(buildUndoDirective(evil)).toBeNull();
    void result.current(evil);
    expect(send).not.toHaveBeenCalled();
  });

  it('respects undo.available === false (blocks even an allowlisted tool)', () => {
    const { result } = renderHook(() => useActivityUndo());
    const unavailable: ActivityEvent = {
      op: 'job.start',
      summary: 'Started translation',
      undo: { available: false, tool: 'chapter_delete' },
    };
    expect(canUndo(unavailable)).toBe(false);
    void result.current(unavailable);
    expect(send).not.toHaveBeenCalled();
  });

  it('blocks an activity with no undo descriptor at all', () => {
    const { result } = renderHook(() => useActivityUndo());
    const none: ActivityEvent = { op: 'z', summary: 'no reverse' };
    expect(canUndo(none)).toBe(false);
    void result.current(none);
    expect(send).not.toHaveBeenCalled();
  });

  it('allowlist contains the documented Tier-A reverse ops', () => {
    expect(ALLOWED_UNDO_TOOLS).toContain('chapter_delete');
    expect(ALLOWED_UNDO_TOOLS).toContain('glossary_restore_revision');
  });
});
