// M2 (newcomer polish F3) — a cross-panel chapter mutation rides the bus so the manuscript
// navigator (hand-rolled tree a react-query invalidation can't reach) reloads. The reducer must
// bump a dedicated seq (mirror planFocusSeq/guidedTourRequestSeq) and disturb nothing else.
import { describe, expect, it } from 'vitest';
import { applyBusEvent, type StudioBusSnapshot } from '../types';

const empty = (): StudioBusSnapshot => ({ revision: 0, bookId: 'b1', activePanelIds: [] });

describe('manuscriptChanged bus event (F3)', () => {
  it('a fresh snapshot has no change seq (never reloads on mount)', () => {
    expect(empty().manuscriptChangeSeq).toBeUndefined();
  });

  it('the first change bumps the seq to 1', () => {
    expect(applyBusEvent(empty(), { type: 'manuscriptChanged' }).manuscriptChangeSeq).toBe(1);
  });

  it('each change monotonically increments the seq (every mutation reloads once)', () => {
    let s = applyBusEvent(empty(), { type: 'manuscriptChanged' });
    s = applyBusEvent(s, { type: 'manuscriptChanged' });
    s = applyBusEvent(s, { type: 'manuscriptChanged' });
    expect(s.manuscriptChangeSeq).toBe(3);
  });

  it('bumps the bus revision like every other event', () => {
    expect(applyBusEvent(empty(), { type: 'manuscriptChanged' }).revision).toBe(1);
  });

  it('does not disturb the active chapter / selection slices', () => {
    let s = applyBusEvent(empty(), { type: 'chapter', chapterId: 'c1', bookId: 'b1' });
    s = applyBusEvent(s, { type: 'manuscriptChanged' });
    expect(s.activeChapterId).toBe('c1'); // a create signal must not clear what's open in the editor
    expect(s.manuscriptChangeSeq).toBe(1);
  });
});
