// Plan Hub redesign — the Advanced lane-flow view (LaneFlowView → FlowLane → FlowChapterCard). Every
// item is exercised against the sealed mockup: authorship coding, status texture, scenes lazy-reveal,
// inline +chapter/+scene/+sub-arc, "+ N more" pagination, sub-arc nesting, machine-arc chip.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { LaneFlowView, type LaneFlowViewProps } from '../LaneFlowView';
import type { LaneArc } from '../../layout/laneTree';

function arc(o: Partial<LaneArc> & { id: string }): LaneArc {
  return {
    kind: 'arc', depth: 0, title: 'Arc', status: 'drafting', source: 'authored',
    span: null, summary: null, isContiguous: true, chapterCount: 0, collapsed: false,
    chapters: [], subArcs: [], ...o,
  };
}

function setup(tree: LaneArc[], o: Partial<LaneFlowViewProps> = {}) {
  const props: LaneFlowViewProps = {
    laneTree: tree,
    arcPagination: {},
    selectedId: null,
    activeChapterId: null,
    onSelect: vi.fn(),
    onToggleArc: vi.fn(),
    onToggleChapter: vi.fn(),
    onLoadMoreArc: vi.fn(),
    onAddChapter: vi.fn(),
    onAddScene: vi.fn(),
    onAddSubArc: vi.fn(),
    addingChild: false,
    childError: null,
    ...o,
  };
  render(<LaneFlowView {...props} />);
  return props;
}

describe('LaneFlowView (Advanced redesign)', () => {
  it('renders a lane per arc with its full title (never truncated) + the arc-subtitle', () => {
    setup([arc({ id: 'a1', title: "Vesna's debt — ORVIS rounds her billed hours down", span: { from_order: 1, to_order: 4 }, chapterCount: 4 })]);
    expect(screen.getByTestId('flow-lane-a1')).toBeTruthy();
    expect(screen.getByText("Vesna's debt — ORVIS rounds her billed hours down")).toBeTruthy();
    expect(screen.getByText(/chapters 1–4/)).toBeTruthy();
  });

  it('codes authorship: an authored lane is serif, a mined lane is mono + carries the AI chip when collapsed', () => {
    setup([
      arc({ id: 'auth', source: 'authored' }),
      arc({ id: 'mined', source: 'mined', collapsed: true, chapterCount: 3 }),
    ]);
    expect(screen.getByTestId('flow-lane-auth').getAttribute('data-source')).toBe('authored');
    const mined = screen.getByTestId('flow-lane-mined');
    expect(mined.getAttribute('data-source')).toBe('mined');
    expect(screen.getByTestId('flow-lane-ai-mined')).toBeTruthy();
  });

  it('a chapter card shows status + title; scenes are hidden until revealed, then load via toggle', () => {
    const onToggleChapter = vi.fn();
    setup([arc({ id: 'a1', chapters: [
      { id: 'c1', chapterId: 'bk1', storyOrder: 0, title: 'The rounding', status: 'done', source: 'authored', written: true, scenes: [], scenesExpanded: false },
    ] })], { onToggleChapter });
    expect(screen.getByTestId('flow-ch-c1').getAttribute('data-status')).toBe('done');
    expect(screen.getByText('The rounding')).toBeTruthy();
    // scenes hidden → a reveal toggle; clicking asks the controller to load them
    fireEvent.click(screen.getByTestId('flow-toggle-scenes-c1'));
    expect(onToggleChapter).toHaveBeenCalledWith('c1');
  });

  it('an EXPANDED chapter shows its scene chips + a "+ scene" add', () => {
    const onAddScene = vi.fn();
    setup([arc({ id: 'a1', chapters: [
      { id: 'c1', chapterId: 'bk1', storyOrder: 0, title: 'Ch', status: 'drafting', source: 'authored', written: false, scenesExpanded: true, scenes: [
        { id: 's1', title: 'Cold open: the fabricator bay', status: 'drafting', source: 'authored', written: false, storyOrder: 1 },
        { id: 's2', title: 'AI: proposed bridge scene', status: 'outline', source: 'mined', written: false, storyOrder: 2 },
      ] },
    ] })], { onAddScene });
    expect(screen.getByText('Cold open: the fabricator bay')).toBeTruthy();
    expect(screen.getByTestId('flow-sc-s2')).toBeTruthy(); // the mined scene renders
    fireEvent.click(screen.getByTestId('flow-add-scene-c1'));
    expect(onAddScene).toHaveBeenCalledWith('c1', 'bk1');
  });

  it('wires "+ chapter" and "+ sub-arc" at the end of a lane', () => {
    const onAddChapter = vi.fn();
    const onAddSubArc = vi.fn();
    setup([arc({ id: 'a1' })], { onAddChapter, onAddSubArc });
    fireEvent.click(screen.getByTestId('flow-add-chapter-a1'));
    expect(onAddChapter).toHaveBeenCalledWith('a1');
    fireEvent.click(screen.getByTestId('flow-add-subarc-a1'));
    expect(onAddSubArc).toHaveBeenCalledWith('a1');
  });

  it('"+ N more" pages the arc window; the count chip shows loaded/total only when there is more', () => {
    const onLoadMoreArc = vi.fn();
    setup([arc({ id: 'a1', chapterCount: 340 })], {
      onLoadMoreArc,
      arcPagination: { a1: { loaded: 100, total: 340, hasMore: true, loading: false } },
    });
    expect(screen.getByTestId('flow-lane-count-a1').textContent).toBe('100/340');
    fireEvent.click(screen.getByTestId('flow-lane-more-a1'));
    expect(onLoadMoreArc).toHaveBeenCalledWith('a1');
  });

  it('renders a non-contiguous warn chip and nests a sub-arc as an inset lane', () => {
    setup([arc({ id: 'a1', isContiguous: false, chapterCount: 4, subArcs: [
      arc({ id: 'sub', depth: 1, title: 'The scavenged compute fails', chapterCount: 1 }),
    ] })]);
    expect(screen.getByTestId('flow-lane-warn-a1')).toBeTruthy();
    expect(screen.getByTestId('flow-lane-sub')).toBeTruthy();
    expect(screen.getByText('The scavenged compute fails')).toBeTruthy();
    expect(screen.getByTestId('flow-subtag-sub')).toBeTruthy(); // the explicit nesting tag
  });

  it('clicking a chapter selects it (→ drawer); a matched card is ringed', () => {
    const onSelect = vi.fn();
    setup([arc({ id: 'a1', chapters: [
      { id: 'c1', chapterId: 'bk1', storyOrder: 0, title: 'Ch', status: 'outline', source: 'authored', written: false, scenes: [], scenesExpanded: false },
    ] })], { onSelect, matchedIds: new Set(['c1']) });
    const card = screen.getByTestId('flow-ch-c1');
    expect(card.className).toContain('ring-2');
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith('c1');
  });

  it('shows a create error and the empty hint when there are no lanes', () => {
    setup([], { childError: 'Could not add the chapter.' });
    expect(screen.getByTestId('flow-child-error').textContent).toContain('Could not add the chapter.');
    expect(screen.getByTestId('flow-empty')).toBeTruthy();
  });
});
