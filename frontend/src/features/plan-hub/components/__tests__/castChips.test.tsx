// 24 PH26 / PH23 — cast chips, and the ABSENCE split that is the whole point of them.
//
//   map COMPLETE + id absent  → MISSING: the reference is genuinely broken (a real problem).
//   map TRUNCATED + id absent → UNKNOWN: we just haven't paged it in. Say nothing; accuse no one.
//
// Collapsing those two would make the Hub report a lost entity over a glossary it had merely not
// finished reading — the `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` class.
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { NodeBadges } from '../NodeBadges';
import { CAST_CHIP_CAP, orderNodeBadges } from '../nodePresentation';
import type { EntityResolution } from '../../hooks/useEntityNames';
import type { NodeContent } from '../../types';

const content = (o: Partial<NodeContent> = {}): NodeContent => ({
  title: 'Sc 1',
  status: 'outline',
  kind: 'scene',
  tension: null,
  beatRole: null,
  chapterId: 'bc-1',
  castIds: [],
  castCount: 0,
  ...o,
});

/** A map that knows `known-*` ids and is COMPLETE — so anything else is genuinely missing. */
const completeMap = (id: string): EntityResolution =>
  id.startsWith('known-') ? { state: 'resolved', name: `Name ${id}` } : { state: 'missing' };

/** A map still paging — an absent id proves nothing. */
const partialMap = (id: string): EntityResolution =>
  id.startsWith('known-') ? { state: 'resolved', name: `Name ${id}` } : { state: 'unknown' };

const NODE = 'sc-1';
const base = { overlay: null, nodeId: NODE };

describe('cast chips (PH26)', () => {
  it('emits a chip per cast id, resolved to a NAME', () => {
    const badges = orderNodeBadges({
      ...base,
      content: content({ castIds: ['known-a', 'known-b'], castCount: 2 }),
      resolveEntity: completeMap,
    });
    render(<NodeBadges nodeId={NODE} badges={badges} />);
    expect(screen.getByTestId(`plan-badge-cast-${NODE}-known-a`).textContent).toContain('Name known-a');
    expect(screen.getByTestId(`plan-badge-cast-${NODE}-known-b`)).toBeTruthy();
  });

  it('COMPLETE map + absent id ⇒ a MISSING warning chip', () => {
    const badges = orderNodeBadges({
      ...base,
      content: content({ castIds: ['ghost'], castCount: 1 }),
      resolveEntity: completeMap,
    });
    render(<NodeBadges nodeId={NODE} badges={badges} />);
    const chip = screen.getByTestId(`plan-badge-cast-${NODE}-ghost`);
    expect(chip.getAttribute('data-cast-state')).toBe('missing');
    expect(chip.textContent).toContain('missing entity');
  });

  it('INCOMPLETE map + absent id ⇒ neutral UNKNOWN, never an accusation', () => {
    const badges = orderNodeBadges({
      ...base,
      content: content({ castIds: ['ghost'], castCount: 1 }),
      resolveEntity: partialMap,
    });
    render(<NodeBadges nodeId={NODE} badges={badges} />);
    const chip = screen.getByTestId(`plan-badge-cast-${NODE}-ghost`);
    expect(chip.getAttribute('data-cast-state')).toBe('unknown');
    expect(chip.textContent).not.toContain('missing'); // the map didn't finish — say nothing
  });

  it('caps at 3 chips and reports the remainder from the EXACT count', () => {
    // The server caps `present_entity_ids` to 3 but keeps `present_entity_count` exact — precisely so
    // a 9-person scene can render "+6" rather than "+0" from the truncated list's length.
    const badges = orderNodeBadges({
      ...base,
      content: content({
        castIds: ['known-a', 'known-b', 'known-c'],
        castCount: 9,
      }),
      resolveEntity: completeMap,
    });
    render(<NodeBadges nodeId={NODE} badges={badges} />);
    expect(screen.getAllByTestId(/plan-badge-cast-/)).toHaveLength(CAST_CHIP_CAP);
    expect(screen.getByTestId(`plan-badge-overflow-cast-${NODE}`).textContent).toBe('+6');
  });

  it('no overflow chip when the roster fits', () => {
    const badges = orderNodeBadges({
      ...base,
      content: content({ castIds: ['known-a'], castCount: 1 }),
      resolveEntity: completeMap,
    });
    render(<NodeBadges nodeId={NODE} badges={badges} />);
    expect(screen.queryByTestId(`plan-badge-overflow-cast-${NODE}`)).toBeNull();
  });

  it('NO resolver ⇒ no cast chips (never a row of raw UUIDs)', () => {
    const badges = orderNodeBadges({
      ...base,
      content: content({ castIds: ['known-a'], castCount: 1 }),
      // resolveEntity omitted
    });
    expect(badges.filter((b) => b.kind === 'cast')).toHaveLength(0);
  });

  it('an empty cast adds nothing', () => {
    const badges = orderNodeBadges({ ...base, content: content(), resolveEntity: completeMap });
    expect(badges).toHaveLength(0);
  });
});
