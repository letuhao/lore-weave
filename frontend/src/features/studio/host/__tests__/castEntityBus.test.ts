// S7 D-CAST-ARC-BUS-SLICE — the cast→arc tier-2 deep-link rides the bus.
//
// CastPanel publishes `castEntity` when a row's "view arc" is clicked; an
// already-open character-arc panel subscribes to `activeCastEntityId` so it
// re-subjects. The reducer must be additive (mirror `arc`/`activeArcId`) and
// never disturb the other bus slices.
import { describe, expect, it } from 'vitest';
import { applyBusEvent, type StudioBusSnapshot } from '../types';

const empty = (): StudioBusSnapshot => ({ revision: 0, bookId: 'b1', activePanelIds: [] });

describe('castEntity bus event (D-CAST-ARC-BUS-SLICE)', () => {
  it('records the selected cast entity id', () => {
    const s = applyBusEvent(empty(), { type: 'castEntity', entityId: 'e42' });
    expect(s.activeCastEntityId).toBe('e42');
  });

  it('a second click replaces the subject (switches an open arc panel)', () => {
    let s = applyBusEvent(empty(), { type: 'castEntity', entityId: 'e42' });
    s = applyBusEvent(s, { type: 'castEntity', entityId: 'e99' });
    expect(s.activeCastEntityId).toBe('e99');
  });

  it('bumps the bus revision like every other event', () => {
    expect(applyBusEvent(empty(), { type: 'castEntity', entityId: 'e42' }).revision).toBe(1);
  });

  it('a fresh snapshot carries no cast entity (no stale replay on mount)', () => {
    expect(empty().activeCastEntityId).toBeUndefined();
  });

  it('does not disturb the arc slice (cast↔arc subjects are independent axes)', () => {
    let s = applyBusEvent(empty(), { type: 'arc', arcId: 'a1' });
    s = applyBusEvent(s, { type: 'castEntity', entityId: 'e42' });
    expect(s.activeArcId).toBe('a1');
    expect(s.activeCastEntityId).toBe('e42');
  });
});
