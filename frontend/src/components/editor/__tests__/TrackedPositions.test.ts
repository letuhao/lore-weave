import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { afterEach, describe, expect, it } from 'vitest';
import {
  TrackedPositionsExtension,
  trackPosition,
  trackRange,
} from '../TrackedPositions';

// Headless editor — locks the WS-C position-remap util: a tracked position/range is
// remapped through every doc change (the position analogue of GrammarPlugin's
// decoration.map), so a saved insert point / selection survives a mid-stream edit
// instead of pointing at the wrong offset. Content '<p>Hello world</p>' → text starts
// at pos 1 ("Hello world" = 11 chars, positions 1..12).

let editor: Editor | null = null;
afterEach(() => { editor?.destroy(); editor = null; });

function mk(): Editor {
  editor = new Editor({
    element: document.createElement('div'),
    extensions: [StarterKit, TrackedPositionsExtension],
    content: '<p>Hello world</p>',
  });
  return editor;
}

describe('TrackedPositions (WS-C — position remap)', () => {
  it('remaps a tracked POSITION through an edit BEFORE it (the corruption the size-check missed)', () => {
    const e = mk();
    const h = trackPosition(e, 7);            // inside the text
    expect(h.current()).toBe(7);
    e.commands.insertContentAt(1, 'XYZ');     // 3 chars BEFORE the tracked pos
    expect(h.current()).toBe(10);             // shifted +3 — not stale, not wrong-offset
    h.release();
  });

  it('an edit AFTER the tracked position leaves it unchanged', () => {
    const e = mk();
    const h = trackPosition(e, 3);
    e.commands.insertContentAt(10, 'ZZZ');    // after the tracked pos
    expect(h.current()).toBe(3);
    h.release();
  });

  it('returns null when the tracked position is deleted', () => {
    const e = mk();
    const h = trackPosition(e, 6);
    e.commands.deleteRange({ from: 5, to: 8 }); // span covers pos 6
    expect(h.current()).toBeNull();
    h.release();
  });

  it('remaps a tracked RANGE through an edit before it', () => {
    const e = mk();
    const h = trackRange(e, 7, 12);           // "world"
    expect(h.current()).toEqual({ from: 7, to: 12 });
    e.commands.insertContentAt(1, 'XYZ');
    expect(h.current()).toEqual({ from: 10, to: 15 });
    h.release();
  });

  it('returns null when the tracked range is fully deleted', () => {
    const e = mk();
    const h = trackRange(e, 7, 12);
    e.commands.deleteRange({ from: 7, to: 12 });
    expect(h.current()).toBeNull();           // collapsed → the precise stale signal
    h.release();
  });

  it('release() stops tracking (current() → null)', () => {
    const e = mk();
    const h = trackPosition(e, 4);
    h.release();
    expect(h.current()).toBeNull();
  });

  it('is inert when nothing is tracked (no error on edits)', () => {
    const e = mk();
    expect(() => e.commands.insertContentAt(1, 'A')).not.toThrow();
  });

  it('release() after the editor is destroyed does not throw (unmount-cleanup guard)', () => {
    const e = mk();
    const h = trackPosition(e, 4);
    e.destroy();              // editor torn down before the handle is released
    editor = null;            // (afterEach already destroyed-safe)
    expect(() => h.release()).not.toThrow();
  });
});
