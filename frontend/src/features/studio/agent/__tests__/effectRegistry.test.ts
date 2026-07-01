import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  registerEffectHandler, matchEffectHandlers, runEffectHandlers, clearEffectHandlers, type EffectContext,
} from '../effectRegistry';
import { bookDraftEffect } from '../handlers/bookEffects';
import type { StudioHost } from '../../host/StudioHostProvider';

beforeEach(() => clearEffectHandlers());

const ctx = (over: Partial<EffectContext> = {}): EffectContext => ({
  tool: 'book_save_chapter_draft',
  result: { chapter_id: 'ch1' },
  bookId: 'b1',
  host: { publish: vi.fn() } as unknown as StudioHost,
  queryClient: { invalidateQueries: vi.fn() } as unknown as EffectContext['queryClient'],
  ...over,
});

describe('effect registry matching', () => {
  it('string pattern matches exact + prefix; RegExp matches by test', () => {
    const s = vi.fn(); const r = vi.fn();
    registerEffectHandler('book_save', s);
    registerEffectHandler(/draft$/, r);
    expect(matchEffectHandlers('book_save')).toContain(s);       // exact
    expect(matchEffectHandlers('book_save_chapter')).toContain(s); // prefix
    expect(matchEffectHandlers('composition_draft')).toContain(r); // regex
    expect(matchEffectHandlers('unrelated_tool')).toHaveLength(0);
  });

  it('runEffectHandlers awaits every matching handler', async () => {
    const a = vi.fn(); const b = vi.fn();
    registerEffectHandler('book_', a);
    registerEffectHandler(/book/, b);
    await runEffectHandlers(ctx({ tool: 'book_x' }));
    expect(a).toHaveBeenCalledOnce();
    expect(b).toHaveBeenCalledOnce();
  });
});

describe('bookDraftEffect (Lane B v1 handler)', () => {
  it('invalidates the chapter query + publishes the chapter to the bus', () => {
    const c = ctx();
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['chapter', 'b1', 'ch1'] });
    expect(c.host.publish).toHaveBeenCalledWith({ type: 'chapter', chapterId: 'ch1', bookId: 'b1' });
  });

  it('G7: skips reload when the chapter hoist is DIRTY (never clobbers unsaved edits)', () => {
    const c = ctx({ isChapterDirty: () => true });
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).not.toHaveBeenCalled();
    expect(c.host.publish).not.toHaveBeenCalled();
  });

  it('no chapter id in the result → no-op (never guesses)', () => {
    const c = ctx({ result: { ok: true } });
    bookDraftEffect(c);
    expect(c.queryClient.invalidateQueries).not.toHaveBeenCalled();
  });
});
