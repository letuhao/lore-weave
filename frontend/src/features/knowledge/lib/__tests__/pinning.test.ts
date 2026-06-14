import { describe, it, expect } from 'vitest';
import type { GlossaryEntityStat } from '../../api';
import {
  autoPinSuggestions,
  distinctKinds,
  entitySpan,
  filterEntities,
  isAutoPinCandidate,
  pinnedWindowTokens,
} from '../pinning';

function stat(p: Partial<GlossaryEntityStat>): GlossaryEntityStat {
  return {
    entity_id: 'e',
    name: 'X',
    kind: 'character',
    mention_count: 1,
    first_chapter_index: null,
    last_chapter_index: null,
    coverage_pct: 0,
    ...p,
  };
}

describe('entitySpan', () => {
  it('is last - first + 1, inclusive', () => {
    expect(entitySpan(stat({ first_chapter_index: 1, last_chapter_index: 50 }))).toBe(50);
    expect(entitySpan(stat({ first_chapter_index: 3, last_chapter_index: 3 }))).toBe(1);
  });
  it('is 0 when an index is null', () => {
    expect(entitySpan(stat({ first_chapter_index: null, last_chapter_index: 5 }))).toBe(0);
  });
});

describe('isAutoPinCandidate', () => {
  it('flags sparse-but-long-reaching (coverage ≤0.15 AND span ≥0.5×count)', () => {
    // 100 chapters; coverage 0.02; span 1..50 = 50 ≥ 50.
    const s = stat({ coverage_pct: 0.02, first_chapter_index: 1, last_chapter_index: 50 });
    expect(isAutoPinCandidate(s, 100)).toBe(true);
  });
  it('rejects dense entities (coverage > 0.15)', () => {
    const s = stat({ coverage_pct: 0.2, first_chapter_index: 1, last_chapter_index: 80 });
    expect(isAutoPinCandidate(s, 100)).toBe(false);
  });
  it('rejects short-reaching entities (span < 0.5×count)', () => {
    // sparse but only spans 1..10 of 100.
    const s = stat({ coverage_pct: 0.05, first_chapter_index: 1, last_chapter_index: 10 });
    expect(isAutoPinCandidate(s, 100)).toBe(false);
  });
  it('never suggests when chapter_count is 0', () => {
    const s = stat({ coverage_pct: 0, first_chapter_index: 1, last_chapter_index: 50 });
    expect(isAutoPinCandidate(s, 0)).toBe(false);
  });
});

describe('autoPinSuggestions', () => {
  it('returns the candidate ids only', () => {
    const stats = [
      stat({ entity_id: 'pangu', coverage_pct: 0.02, first_chapter_index: 1, last_chapter_index: 50 }),
      stat({ entity_id: 'kai', coverage_pct: 0.3, first_chapter_index: 1, last_chapter_index: 90 }),
    ];
    expect(autoPinSuggestions(stats, 100)).toEqual(['pangu']);
  });
});

describe('filterEntities', () => {
  const stats = [
    stat({ entity_id: 'a', name: 'PanGu', kind: 'deity', mention_count: 2 }),
    stat({ entity_id: 'b', name: 'Kai', kind: 'character', mention_count: 30 }),
    stat({ entity_id: 'c', name: 'Pangolin', kind: 'creature', mention_count: 5 }),
  ];
  it('search is case-insensitive substring on name', () => {
    expect(filterEntities(stats, { search: 'pan', kind: '', minMentions: 0 }).map((s) => s.entity_id)).toEqual(['a', 'c']);
  });
  it('kind filters exactly', () => {
    expect(filterEntities(stats, { search: '', kind: 'character', minMentions: 0 }).map((s) => s.entity_id)).toEqual(['b']);
  });
  it('minMentions is a floor', () => {
    expect(filterEntities(stats, { search: '', kind: '', minMentions: 5 }).map((s) => s.entity_id)).toEqual(['b', 'c']);
  });
});

describe('distinctKinds', () => {
  it('returns sorted unique kinds', () => {
    const stats = [stat({ kind: 'deity' }), stat({ kind: 'character' }), stat({ kind: 'deity' })];
    expect(distinctKinds(stats)).toEqual(['character', 'deity']);
  });
});

describe('pinnedWindowTokens', () => {
  it('is count × 50', () => {
    expect(pinnedWindowTokens(3)).toBe(150);
    expect(pinnedWindowTokens(0)).toBe(0);
  });
});
