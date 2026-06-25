import { describe, expect, it, vi } from 'vitest';
import { openPopoutChannel, popoutChannelName, type PopoutMessage } from '../popoutChannel';

describe('popoutChannel (T5.4 M4)', () => {
  it('names the channel per-(book, chapter) so books AND chapters do not cross wires', () => {
    expect(popoutChannelName('book-a', 'c1')).not.toBe(popoutChannelName('book-b', 'c1'));
    expect(popoutChannelName('book-a', 'c1')).not.toBe(popoutChannelName('book-a', 'c2'));
    expect(popoutChannelName('book-a', 'c1')).toContain('book-a');
    expect(popoutChannelName('book-a', 'c1')).toContain('c1');
  });

  it('delivers a posted message to a subscriber on the SAME book+chapter channel', async () => {
    // jsdom/Node provides BroadcastChannel; two instances on the same name talk.
    // NOTE: ids are file-unique (PCHAN_*) — Node shares BroadcastChannel across vitest
    // worker threads, so a generic 'b1'/'c1' would cross-talk with the other popout
    // test files (which post dock-back on the same name) and break this strict toEqual.
    const opener = openPopoutChannel('PCHAN_b1', 'c1');
    const popout = openPopoutChannel('PCHAN_b1', 'c1');
    const got: PopoutMessage[] = [];
    opener.subscribe((m) => got.push(m));
    popout.post({ kind: 'insert-prose', text: 'hello', model: 'gpt' });
    await new Promise((r) => setTimeout(r, 0));   // BroadcastChannel delivers async
    expect(got).toEqual([{ kind: 'insert-prose', text: 'hello', model: 'gpt' }]);
    opener.close();
    popout.close();
  });

  it('does NOT deliver across different book channels', async () => {
    const a = openPopoutChannel('PCHAN_bookA', 'c1');
    const b = openPopoutChannel('PCHAN_bookB', 'c1');
    const got: PopoutMessage[] = [];
    a.subscribe((m) => got.push(m));
    b.post({ kind: 'dock-back', panel: 'cast' });
    await new Promise((r) => setTimeout(r, 0));
    expect(got).toEqual([]);
    a.close();
    b.close();
  });

  it('does NOT deliver across different CHAPTERS of the same book (/review-impl MED)', async () => {
    const ch1 = openPopoutChannel('PCHAN_bk', 'c1');
    const ch2 = openPopoutChannel('PCHAN_bk', 'c2');
    const got: PopoutMessage[] = [];
    ch1.subscribe((m) => got.push(m));
    ch2.post({ kind: 'insert-prose', text: 'for chapter 2', model: undefined });
    await new Promise((r) => setTimeout(r, 0));
    expect(got).toEqual([]);   // chapter 1's editor must NOT receive chapter 2's prose
    ch1.close();
    ch2.close();
  });

  it('unsubscribe stops delivery', async () => {
    const opener = openPopoutChannel('PCHAN_b2', 'c1');
    const popout = openPopoutChannel('PCHAN_b2', 'c1');
    const handler = vi.fn();
    const unsub = opener.subscribe(handler);
    unsub();
    popout.post({ kind: 'dock-back', panel: 'compose' });
    await new Promise((r) => setTimeout(r, 0));
    expect(handler).not.toHaveBeenCalled();
    opener.close();
    popout.close();
  });
});
