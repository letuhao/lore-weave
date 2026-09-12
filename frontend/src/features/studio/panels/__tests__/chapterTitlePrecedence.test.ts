import { readFileSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { describe, it, expect } from 'vitest';

// T18 — one chapter-title precedence, used by every panel that lists chapters.
//
// A 2026-09-06 human-sim run found the Conformance panel's chapter picker rendering
// "Untitled chapter" for all 28 chapters of a book whose titles rendered correctly in the
// sidebar tree one panel away. The cause was its own field precedence,
// `c.title || c.original_filename || #sort_order`, instead of the shared `chapterDisplayTitle()`
// helper — which deliberately never falls back to a STORAGE FILENAME, because a filename is not a
// title and showing one tells the author their chapter is called something it is not.
//
// The reason this is a mechanical gate and not three fixed call sites: the defect had been
// COPY-PASTED into three panels (Conformance, Critic, Heal). Fixing three occurrences leaves the
// fourth free to be written tomorrow, and nothing would notice — NV-3, "the scope never reaches
// it". Per SDK-First SDK-1, two users of a rule means one shared implementation, not two copies.
//
// Scope mirrors dockablePanelHygiene.test.ts: panels/** only, the panels themselves.

const PANELS_DIR = resolve(__dirname, '..');

function panelSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      return entry.name === '__tests__' ? [] : panelSourceFiles(join(dir, entry.name));
    }
    return entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')
      ? [join(dir, entry.name)]
      : [];
  });
}

/** A hand-rolled title fallback: any expression that reaches for `original_filename` as a
 *  chapter's display name. The filename is the one fallback `chapterDisplayTitle` refuses. */
const FILENAME_FALLBACK = /\.title\s*\|\|[^\n]*original_filename/;

describe('T18 — chapter title precedence lives in one place', () => {
  const files = panelSourceFiles(PANELS_DIR);

  it('finds panel sources to scan (without this the gate is vacuous)', () => {
    expect(files.length).toBeGreaterThan(5);
  });

  it('no panel hand-rolls a title fallback through original_filename', () => {
    const offenders = files.filter((f) => FILENAME_FALLBACK.test(readFileSync(f, 'utf8')));
    expect(
      offenders.map((f) => f.replace(PANELS_DIR, 'panels')),
      'a panel renders a storage filename as a chapter title instead of calling '
        + 'chapterDisplayTitle() — that is what showed "Untitled chapter" for 28 named chapters',
    ).toEqual([]);
  });

  it('the three panels that carried the defect now call the shared helper', () => {
    // Named explicitly as well as scanned: the regex above proves the BAD shape is gone, this
    // proves the GOOD one arrived. A panel could satisfy the first by dropping the label entirely.
    for (const name of ['QualityConformancePanel', 'QualityCriticPanel', 'QualityHealPanel']) {
      const src = readFileSync(join(PANELS_DIR, `${name}.tsx`), 'utf8');
      expect(src, `${name} should render chapters via chapterDisplayTitle()`).toContain(
        'chapterDisplayTitle(c)',
      );
    }
  });

  it('the pattern it scans for can actually match (NV-2)', () => {
    // A regex that matches nothing would make the scan above pass on any codebase at all.
    expect(FILENAME_FALLBACK.test('{c.title || c.original_filename || `#${c.sort_order}`}')).toBe(
      true,
    );
    expect(FILENAME_FALLBACK.test('{chapterDisplayTitle(c)}')).toBe(false);
  });
});
