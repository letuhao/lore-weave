import { describe, it, expect, beforeEach } from 'vitest';
import { registerEditorTarget, getEditorTarget } from '../context/editorBridge';
import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';

// ARCH-1 C6 — the editor bridge: the editor page registers its chapter + Tiptap
// handle ref; the chat Apply handler reads the live target.

function fakeHandle(): TiptapEditorHandle {
  return {
    setContent: () => {},
    setGrammarEnabled: () => {},
    setSourceView: () => {},
    setGlossaryEntities: () => {},
    setGlossaryEnabled: () => {},
    getGlossaryCount: () => 0,
    getSelection: () => ({ from: 0, to: 0, empty: true, text: '' }),
    insertAtCursor: () => true,
    replaceSelection: () => false,
  };
}

describe('editorBridge', () => {
  beforeEach(() => registerEditorTarget(null));

  it('returns null when nothing is registered', () => {
    expect(getEditorTarget()).toBeNull();
  });

  it('returns the live handle from the registered ref', () => {
    const handle = fakeHandle();
    registerEditorTarget({ bookId: 'b1', chapterId: 'ch1', handleRef: { current: handle } });
    const target = getEditorTarget();
    expect(target).not.toBeNull();
    expect(target!.bookId).toBe('b1');
    expect(target!.chapterId).toBe('ch1');
    expect(target!.handle).toBe(handle);
  });

  it('returns null when the handle ref is not yet mounted', () => {
    registerEditorTarget({ bookId: 'b1', chapterId: 'ch1', handleRef: { current: null } });
    expect(getEditorTarget()).toBeNull();
  });

  it('clears on null registration (unmount / chapter change)', () => {
    registerEditorTarget({ bookId: 'b1', chapterId: 'ch1', handleRef: { current: fakeHandle() } });
    registerEditorTarget(null);
    expect(getEditorTarget()).toBeNull();
  });

  it('reads the LATEST registered target (chapter switch)', () => {
    const h1 = fakeHandle();
    const h2 = fakeHandle();
    registerEditorTarget({ bookId: 'b1', chapterId: 'ch1', handleRef: { current: h1 } });
    registerEditorTarget({ bookId: 'b1', chapterId: 'ch2', handleRef: { current: h2 } });
    const target = getEditorTarget();
    expect(target!.chapterId).toBe('ch2');
    expect(target!.handle).toBe(h2);
  });
});
