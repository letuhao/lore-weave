// 24 §Phase H6 / PH25 — the Plan navigator rail. Two proofs: (1) flattenArcShell derives depth from
// the parent_id TREE (not the shell's own `depth` field) and orders siblings by rank; (2) the rail
// renders the shell indented by that depth and a row click fires the hub-focus contract
// (onFocusNode with the node id) — the delta vs the Manuscript Navigator's open-in-Editor click.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ArcListNode } from '../../types';
import { renderWithClient } from '@/test-utils/renderWithClient';
import { flattenArcShell } from '../../hooks/usePlanNavigator';
import { PlanNavigatorRail } from '../PlanNavigatorRail';

const getArcs = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/plan-hub/api', () => ({ getArcs: (...a: unknown[]) => getArcs(...a) }));

const arc = (id: string, o: Partial<ArcListNode> = {}): ArcListNode => ({
  id, kind: 'arc', parent_id: null, depth: 0, rank: 'm', title: `T-${id}`, status: 'planned',
  version: 1, span: null, is_contiguous: true, chapter_count: 0, ...o,
});

beforeEach(() => getArcs.mockReset());

describe('flattenArcShell (PH25)', () => {
  it('derives depth from the parent_id tree, not the shell depth field, and orders by rank', () => {
    // Deliberately-wrong `depth` values prove the tree recomputes them (laneLayout parity: the
    // shell's depth is never trusted). Ranks/order are shuffled to prove rank sorting.
    const shell: ArcListNode[] = [
      arc('sub-b', { parent_id: 'arc-1', depth: 99, rank: 'z' }),
      arc('sub-a', { parent_id: 'arc-1', depth: 99, rank: 'a' }),
      arc('arc-1', { parent_id: 'saga', depth: 0, rank: 'm' }),
      arc('saga', { kind: 'saga', parent_id: null, depth: 7, rank: 'm' }),
    ];
    const rows = flattenArcShell(shell, new Set());
    expect(rows.map((r) => [r.node.id, r.depth])).toEqual([
      ['saga', 0], ['arc-1', 1], ['sub-a', 2], ['sub-b', 2],
    ]);
    expect(rows[0].hasChildren).toBe(true); // saga → arc-1
    expect(rows[2].hasChildren).toBe(false); // leaf sub-arc
  });

  it('a collapsed node hides its subtree', () => {
    const shell: ArcListNode[] = [
      arc('saga', { kind: 'saga', rank: 'a' }),
      arc('arc-1', { parent_id: 'saga', rank: 'a' }),
      arc('sub-a', { parent_id: 'arc-1', rank: 'a' }),
    ];
    const rows = flattenArcShell(shell, new Set(['arc-1']));
    expect(rows.map((r) => r.node.id)).toEqual(['saga', 'arc-1']); // sub-a suppressed
    expect(rows.find((r) => r.node.id === 'arc-1')!.expanded).toBe(false);
  });

  it('a parent_id pointing outside the shell is treated as a root (never dropped)', () => {
    const rows = flattenArcShell([arc('orphan', { parent_id: 'missing' })], new Set());
    expect(rows.map((r) => [r.node.id, r.depth])).toEqual([['orphan', 0]]);
  });
});

describe('PlanNavigatorRail (PH25)', () => {
  const shell: ArcListNode[] = [
    arc('saga', { kind: 'saga', rank: 'a', title: 'Saga One', chapter_count: 9 }),
    arc('arc-1', { parent_id: 'saga', rank: 'a', title: 'Arc One', chapter_count: 4 }),
    arc('sub-a', { parent_id: 'arc-1', rank: 'a', title: 'Sub A', chapter_count: 2 }),
  ];

  it('renders the arc tree indented by depth with chapter-count badges', async () => {
    getArcs.mockResolvedValue({ arcs: shell });
    renderWithClient(<PlanNavigatorRail bookId="b1" onFocusNode={vi.fn()} selectedId={null} />);
    await waitFor(() => expect(screen.getByTestId('plan-nav-row-saga')).toBeInTheDocument());

    const pad = (id: string) =>
      parseInt((screen.getByTestId(`plan-nav-row-${id}`) as HTMLElement).style.paddingLeft, 10);
    // Strictly increasing indentation down the saga → arc → sub-arc chain.
    expect(pad('saga')).toBeLessThan(pad('arc-1'));
    expect(pad('arc-1')).toBeLessThan(pad('sub-a'));
    // depth is surfaced for the assertion + the count badge renders the node's own chapter_count.
    expect(screen.getByTestId('plan-nav-row-sub-a').getAttribute('data-depth')).toBe('2');
    expect(screen.getByTestId('plan-nav-count-arc-1').textContent).toBe('4');
    expect(getArcs).toHaveBeenCalledWith('b1', 'tok');
  });

  it('a row click fires onFocusNode with the node id (hub-focus contract, not an editor open)', async () => {
    const onFocusNode = vi.fn();
    getArcs.mockResolvedValue({ arcs: shell });
    renderWithClient(<PlanNavigatorRail bookId="b1" onFocusNode={onFocusNode} selectedId={null} />);
    await waitFor(() => expect(screen.getByTestId('plan-nav-focus-arc-1')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('plan-nav-focus-arc-1'));
    expect(onFocusNode).toHaveBeenCalledWith('arc-1');
  });

  it('the caret toggles a node without focusing it', async () => {
    const onFocusNode = vi.fn();
    getArcs.mockResolvedValue({ arcs: shell });
    renderWithClient(<PlanNavigatorRail bookId="b1" onFocusNode={onFocusNode} selectedId={null} />);
    await waitFor(() => expect(screen.getByTestId('plan-nav-row-sub-a')).toBeInTheDocument());

    // Collapse the arc → its sub-arc disappears; focus is NOT called (caret is a separate button).
    fireEvent.click(screen.getByTestId('plan-nav-caret-arc-1'));
    await waitFor(() => expect(screen.queryByTestId('plan-nav-row-sub-a')).toBeNull());
    expect(onFocusNode).not.toHaveBeenCalled();
  });

  it('highlights the selected node', async () => {
    getArcs.mockResolvedValue({ arcs: shell });
    renderWithClient(<PlanNavigatorRail bookId="b1" onFocusNode={vi.fn()} selectedId="arc-1" />);
    await waitFor(() => expect(screen.getByTestId('plan-nav-row-arc-1')).toBeInTheDocument());
    // the selected row carries the bg-primary highlight; a non-selected sibling does not.
    expect(screen.getByTestId('plan-nav-row-arc-1').className).toContain('bg-primary');
    expect(screen.getByTestId('plan-nav-row-saga').className).not.toContain('bg-primary');
  });

  // F8 — the empty rail is a real door, not the "No arcs yet." dead end the newcomer hit. The CTA
  // fires the open-plan handoff (StudioSideBar wires it to host.openPanel('plan-hub')).
  it('the empty state renders a "Plan this book" CTA that fires onOpenPlan', async () => {
    const onOpenPlan = vi.fn();
    getArcs.mockResolvedValue({ arcs: [] });
    renderWithClient(<PlanNavigatorRail bookId="b1" onFocusNode={vi.fn()} selectedId={null} onOpenPlan={onOpenPlan} />);
    const cta = await screen.findByTestId('plan-nav-plan-cta');
    fireEvent.click(cta);
    expect(onOpenPlan).toHaveBeenCalledTimes(1);
  });

  // Degrade-safe: without an onOpenPlan the empty state is copy-only — never a broken/no-op button.
  it('the empty state shows guided copy but NO CTA when onOpenPlan is absent', async () => {
    getArcs.mockResolvedValue({ arcs: [] });
    renderWithClient(<PlanNavigatorRail bookId="b1" onFocusNode={vi.fn()} selectedId={null} />);
    await waitFor(() => expect(screen.getByTestId('plan-nav-empty')).toBeInTheDocument());
    expect(screen.queryByTestId('plan-nav-plan-cta')).toBeNull();
  });
});
