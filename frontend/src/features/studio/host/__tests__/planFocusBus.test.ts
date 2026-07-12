// 24 PH25 — the Plan rail's focus request rides the bus.
//
// The rail is an ACTIVITY BAR surface: it lives outside the dock, so it cannot hand the Plan Hub a
// callback. It asks over the bus, and the Hub diffs the SEQ (not the node id) — because re-clicking
// the same row must still pan, and a fresh mount must never replay a stale request.
import { describe, expect, it } from 'vitest';
import { applyBusEvent, type StudioBusSnapshot } from '../types';

const empty = (): StudioBusSnapshot => ({ revision: 0, bookId: 'b1', activePanelIds: [] });

describe('planFocusNode bus event (PH25)', () => {
  it('records the node and starts the seq', () => {
    const s = applyBusEvent(empty(), { type: 'planFocusNode', nodeId: 'n1' });
    expect(s.planFocusNodeId).toBe('n1');
    expect(s.planFocusSeq).toBe(1);
  });

  it('re-focusing the SAME node still bumps the seq — else the second click would do nothing', () => {
    let s = applyBusEvent(empty(), { type: 'planFocusNode', nodeId: 'n1' });
    s = applyBusEvent(s, { type: 'planFocusNode', nodeId: 'n1' });
    expect(s.planFocusNodeId).toBe('n1');
    expect(s.planFocusSeq).toBe(2); // the id is unchanged; only the seq proves a NEW request
  });

  it('a fresh snapshot carries NO seq, so a mounting Hub replays nothing', () => {
    expect(empty().planFocusSeq).toBeUndefined();
  });

  it('bumps the bus revision like every other event', () => {
    const s = applyBusEvent(empty(), { type: 'planFocusNode', nodeId: 'n1' });
    expect(s.revision).toBe(1);
  });

  it('does not disturb the manuscript slice (the two rails are independent)', () => {
    // PH25's whole point: Manuscript row → the Editor; Plan row → the Hub canvas. A plan focus must
    // not move the editor's active chapter, or the two rails become ambiguous.
    let s = applyBusEvent(empty(), { type: 'chapter', chapterId: 'ch-9', bookId: 'b1' });
    s = applyBusEvent(s, { type: 'planFocusNode', nodeId: 'n1' });
    expect(s.activeChapterId).toBe('ch-9');
  });
});
