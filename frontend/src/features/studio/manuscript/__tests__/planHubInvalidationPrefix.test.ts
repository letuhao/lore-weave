import { readFileSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { describe, it, expect } from 'vitest';

// T19 — a mutation that changes the plan must invalidate the plan-hub PREFIX, not one slice of it.
//
// `useChapterDoor` invalidated only `['plan-hub','simple-chapters', bookId]`, so a chapter created
// through that door was invisible on the advanced canvas (`arcs` / `overlay` / `scene-links` / the
// per-node windows) and in the Unplanned tray (`book-chapters`) until a full page reload. A
// 2026-09-06 run recorded it as the canvas "not live-updating"; the write had succeeded every time.
//
// Four sibling mutations already did this correctly (usePlanChildCreate, usePlanMoves,
// usePlanNodeWrites, useExtractPlan) — which is what makes a narrow key here a DIVERGENCE rather
// than a considered choice, and why a mechanical check is worth more than fixing the one hook:
// the next mutation added is free to narrow it again and nothing would notice (NV-3).

const ROOTS = [
  resolve(__dirname, '../..', 'manuscript'),
  resolve(__dirname, '../../../plan-hub'),
];

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    if (e.isDirectory()) return e.name === '__tests__' ? [] : sources(join(dir, e.name));
    return e.name.endsWith('.ts') || e.name.endsWith('.tsx') ? [join(dir, e.name)] : [];
  });
}

/** A plan-hub invalidation narrowed past the prefix: `queryKey: ['plan-hub', '<slice>'…` */
const NARROW = /invalidateQueries\(\s*\{\s*queryKey:\s*\[\s*'plan-hub'\s*,/;

describe('T19 — plan-hub invalidations use the prefix', () => {
  const files = ROOTS.flatMap(sources);

  it('finds sources to scan (without this the check is vacuous)', () => {
    expect(files.length).toBeGreaterThan(5);
  });

  it('no mutation invalidates a single plan-hub slice', () => {
    const offenders = files
      .filter((f) => NARROW.test(readFileSync(f, 'utf8')))
      .map((f) => f.split(/[\/]/).slice(-2).join('/'));
    expect(
      offenders,
      'a mutation refreshes ONE plan-hub slice, so the other consumers (canvas arcs/overlay/'
        + 'scene-links/windows, and the Unplanned tray) stay stale until a full page reload',
    ).toEqual([]);
  });

  it('the pattern it scans for can actually match (NV-2)', () => {
    expect(NARROW.test("qc.invalidateQueries({ queryKey: ['plan-hub', 'simple-chapters', bookId] })")).toBe(true);
    expect(NARROW.test("qc.invalidateQueries({ queryKey: ['plan-hub'] })")).toBe(false);
  });
});
