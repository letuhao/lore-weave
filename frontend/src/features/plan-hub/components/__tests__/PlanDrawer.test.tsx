// 24 H3 / PH16 — PlanDrawer renders the right facet set per node kind + the loading / empty states.
// usePlanNode (the per-node fetch controller) is mocked so the component test stays render-only and
// needs no QueryClient/auth wiring — the fetch/roster logic is the hook's own concern.
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OutlineNode } from '@/features/composition/types';
import type { ArcListNode } from '../../types';
import type { PlanNodeView } from '../../hooks/usePlanNode';

const hook = vi.hoisted(() => ({ usePlanNode: vi.fn() }));
vi.mock('../../hooks/usePlanNode', () => ({ usePlanNode: hook.usePlanNode }));

import { PlanDrawer } from '../PlanDrawer';

function view(o: Partial<PlanNodeView>): PlanNodeView {
  return {
    kind: 'unknown',
    outlineNode: null,
    arcNode: null,
    loading: false,
    error: null,
    nameFor: (id) => (id ? `name:${id}` : null),
    ...o,
  };
}

function outline(o: Partial<OutlineNode> & { id: string; kind: OutlineNode['kind'] }): OutlineNode {
  return {
    project_id: 'p', parent_id: null, rank: 'm', title: 'Untitled', chapter_id: null,
    story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, beat_role: null,
    ...o,
  };
}

function arc(o: Partial<ArcListNode> & { id: string }): ArcListNode {
  return {
    kind: 'arc', parent_id: null, depth: 0, rank: 'm', title: o.id, status: 'active', version: 1,
    span: null, is_contiguous: true, chapter_count: 0, ...o,
  };
}

beforeEach(() => hook.usePlanNode.mockReset());

describe('PlanDrawer', () => {
  it('renders nothing when nothing is selected', () => {
    hook.usePlanNode.mockReturnValue(view({}));
    const { container } = render(<PlanDrawer selectedId={null} kind={null} bookId="b" onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('plan-drawer')).toBeNull();
  });

  it('chapter/scene: renders Overview/Cast/Craft facets from the outline node + resolved cast names', () => {
    hook.usePlanNode.mockReturnValue(
      view({
        kind: 'scene',
        outlineNode: outline({
          id: 'n1', kind: 'scene', title: 'The Summons', status: 'drafting',
          goal: 'Reach the gate', synopsis: 'She crosses the river.', beat_role: 'inciting', tension: 70,
          pov_entity_id: 'e-hero', present_entity_ids: ['e-hero', 'e-foil'], location_entity_id: 'e-gate',
          conflict: 'guarded gate', outcome: 'passes', stakes: 'time', story_time: 'dusk',
          value_shift: -20, target_words: 1200,
        }),
      }),
    );
    render(<PlanDrawer selectedId="n1" kind="scene" bookId="b" onClose={vi.fn()} />);

    // Header + the full facet set.
    expect(screen.getByTestId('plan-drawer-title').textContent).toContain('The Summons');
    expect(screen.getByTestId('plan-drawer-section-overview')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-section-cast')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-section-craft')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-section-canon')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-section-references')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-section-critic')).toBeInTheDocument();

    // Fields render their values; cast ids resolve to names via nameFor.
    expect(screen.getByTestId('plan-drawer-f-goal').textContent).toContain('Reach the gate');
    expect(screen.getByTestId('plan-drawer-f-tension').textContent).toContain('70');
    expect(screen.getByTestId('plan-drawer-f-pov').textContent).toContain('name:e-hero');
    expect(screen.getByTestId('plan-drawer-f-present').textContent).toContain('name:e-hero');
    expect(screen.getByTestId('plan-drawer-f-present').textContent).toContain('name:e-foil');
    expect(screen.getByTestId('plan-drawer-f-conflict').textContent).toContain('guarded gate');
    expect(screen.getByTestId('plan-drawer-f-valueshift').textContent).toContain('-20');

    // No arc-only facets on an outline node.
    expect(screen.queryByTestId('plan-drawer-section-roster')).toBeNull();
    expect(screen.queryByTestId('plan-drawer-arc-gap')).toBeNull();
  });

  it('arc/saga: renders the minimal arc summary + the reuse-gap note, not outline facets', () => {
    hook.usePlanNode.mockReturnValue(
      view({
        kind: 'arc',
        arcNode: arc({
          id: 'A1', kind: 'arc', title: 'Rising Action', status: 'active', goal: 'escalate',
          span: { from_order: 3, to_order: 9 }, is_contiguous: false, chapter_count: 6,
        }),
      }),
    );
    render(<PlanDrawer selectedId="A1" kind="arc" bookId="b" onClose={vi.fn()} />);

    expect(screen.getByTestId('plan-drawer-title').textContent).toContain('Rising Action');
    expect(screen.getByTestId('plan-drawer-section-structure')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-section-roster')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-f-chaptercount').textContent).toContain('6');
    expect(screen.getByTestId('plan-drawer-f-span').textContent).toContain('3');
    // Non-contiguous span is surfaced, and the arc-inspector reuse gap is noted honestly.
    expect(screen.getByTestId('plan-drawer-noncontiguous')).toBeInTheDocument();
    expect(screen.getByTestId('plan-drawer-arc-gap')).toBeInTheDocument();
    // No outline craft facet on an arc.
    expect(screen.queryByTestId('plan-drawer-section-craft')).toBeNull();
  });

  it('shows the loading state while the node fetch is in flight', () => {
    hook.usePlanNode.mockReturnValue(view({ kind: 'chapter', loading: true }));
    render(<PlanDrawer selectedId="n1" kind="chapter" bookId="b" onClose={vi.fn()} />);
    expect(screen.getByTestId('plan-drawer-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('plan-drawer-section-overview')).toBeNull();
  });

  it('shows the error state when the fetch failed', () => {
    hook.usePlanNode.mockReturnValue(view({ kind: 'chapter', error: 'boom' }));
    render(<PlanDrawer selectedId="n1" kind="chapter" bookId="b" onClose={vi.fn()} />);
    expect(screen.getByTestId('plan-drawer-error').textContent).toContain('boom');
  });

  it('shows the empty state for a resolved-but-absent outline node', () => {
    hook.usePlanNode.mockReturnValue(view({ kind: 'chapter', outlineNode: null, loading: false }));
    render(<PlanDrawer selectedId="n1" kind="chapter" bookId="b" onClose={vi.fn()} />);
    expect(screen.getByTestId('plan-drawer-empty')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn();
    hook.usePlanNode.mockReturnValue(view({ kind: 'scene', outlineNode: outline({ id: 'n1', kind: 'scene' }) }));
    render(<PlanDrawer selectedId="n1" kind="scene" bookId="b" onClose={onClose} />);
    screen.getByTestId('plan-drawer-close').click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
