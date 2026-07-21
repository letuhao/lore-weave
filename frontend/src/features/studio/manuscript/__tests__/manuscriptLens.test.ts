import { describe, expect, it } from 'vitest';

import { chooseManuscriptLens, showLensToggle } from '../manuscriptLens';

describe('chooseManuscriptLens (mode-by-content + toggle)', () => {
  it('is pending until the structure resolves', () => {
    expect(chooseManuscriptLens(null, null)).toBe('pending');
    expect(chooseManuscriptLens(null, 'outline')).toBe('pending');
  });

  it('parts-only → parts (the toggle choice is ignored — a book with one lens can never be hidden)', () => {
    expect(chooseManuscriptLens({ parts: true, outline: false }, null)).toBe('parts');
    expect(chooseManuscriptLens({ parts: true, outline: false }, 'outline')).toBe('parts');
  });

  it('outline-only → outline (a planned book keeps its arc/scene view — the no-regression case)', () => {
    expect(chooseManuscriptLens({ parts: false, outline: true }, null)).toBe('outline');
    expect(chooseManuscriptLens({ parts: false, outline: true }, 'parts')).toBe('outline');
  });

  it('neither → flat (plain chapter list, no Unassigned banner)', () => {
    expect(chooseManuscriptLens({ parts: false, outline: false }, null)).toBe('flat');
  });

  it('BOTH → the user toggle, defaulting to parts (THE Bug-4 book: a Part on a Work-backed book is reachable)', () => {
    expect(chooseManuscriptLens({ parts: true, outline: true }, null)).toBe('parts');
    expect(chooseManuscriptLens({ parts: true, outline: true }, 'parts')).toBe('parts');
    expect(chooseManuscriptLens({ parts: true, outline: true }, 'outline')).toBe('outline');
  });
});

describe('showLensToggle', () => {
  it('offers the toggle ONLY when a book has both parts and an outline', () => {
    expect(showLensToggle({ parts: true, outline: true })).toBe(true);
    expect(showLensToggle({ parts: true, outline: false })).toBe(false);
    expect(showLensToggle({ parts: false, outline: true })).toBe(false);
    expect(showLensToggle({ parts: false, outline: false })).toBe(false);
    expect(showLensToggle(null)).toBe(false);
  });
});
