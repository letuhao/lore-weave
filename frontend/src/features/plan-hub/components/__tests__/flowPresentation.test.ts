// Plan Hub redesign — the pure lane-flow presentation helpers.
import { describe, expect, it } from 'vitest';
import { arcSubtitle, chapterCardClass, normStatus, statusDotClass } from '../flowPresentation';
import type { LaneArc } from '../../layout/laneTree';

function arc(o: Partial<LaneArc>): LaneArc {
  return {
    id: 'a', kind: 'arc', depth: 0, title: 'A', status: 'drafting', source: 'authored',
    span: null, summary: null, isContiguous: true, chapterCount: 0, collapsed: false,
    chapters: [], subArcs: [], ...o,
  };
}

describe('arcSubtitle', () => {
  it('composes span · summary · non-contiguous · sub-arc count in that order', () => {
    const a = arc({
      span: { from_order: 3, to_order: 7 }, summary: 'freedom is killing it',
      isContiguous: false, subArcs: [arc({ id: 's' })],
    });
    expect(arcSubtitle(a)).toBe('chapters 3–7 · freedom is killing it · non-contiguous · 1 sub-arc');
  });

  it('a single-chapter span reads "chapter N"; an empty arc has no span segment', () => {
    expect(arcSubtitle(arc({ span: { from_order: 2, to_order: 2 } }))).toBe('chapter 2');
    expect(arcSubtitle(arc({ span: null }))).toBe('');
  });

  it('a mined arc announces it was planner-proposed', () => {
    expect(arcSubtitle(arc({ source: 'mined' }))).toBe('planner proposed');
  });
});

describe('status maps', () => {
  it('normalises unknown status to outline', () => {
    expect(normStatus('done')).toBe('done');
    expect(normStatus('weird')).toBe('outline');
  });

  it('empty is a dashed transparent card; done is success-tinted', () => {
    expect(chapterCardClass('empty')).toContain('border-dashed');
    expect(chapterCardClass('done')).toContain('success');
    expect(statusDotClass('drafting')).toContain('bg-primary');
  });
});
