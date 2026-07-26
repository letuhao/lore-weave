// 24 PH16/PH18 — the drawer's Canon-here + Open-threads facets and their deep-links.
//
// These facets used to read "loads in H4" — long AFTER H4 had shipped. The refs were sitting in the
// very overlay the same controller already held; the drawer just never received it. A stub that
// outlives its blocker is indistinguishable from an unbuilt feature.
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OutlineNode } from '@/features/composition/types';
import type { PlanOverlay } from '../../types';
import type { PlanNodeView } from '../../hooks/usePlanNode';

const hook = vi.hoisted(() => ({ usePlanNode: vi.fn() }));
vi.mock('../../hooks/usePlanNode', () => ({ usePlanNode: hook.usePlanNode }));

import { PlanDrawer } from '../PlanDrawer';

const NODE = 'ch-1';

function outline(): OutlineNode {
  return {
    id: NODE, kind: 'chapter', project_id: 'p', parent_id: null, rank: 'm', title: 'Ch 1',
    chapter_id: 'bc-1', story_order: 1000, status: 'outline', synopsis: '', version: 1,
    is_archived: false, beat_role: null,
  } as OutlineNode;
}

function overlayWith(o: Partial<PlanOverlay['problems']['by_node'][string]>, capped = false): PlanOverlay {
  return {
    problems: {
      by_node: { [NODE]: { canon: 0, threads_open: 0, refs: [], ...o } },
      refs_capped: capped,
    },
    tension_rollup: [],
    motif_chips: [],
    unplanned_chapters: [],
  };
}

beforeEach(() => {
  hook.usePlanNode.mockReturnValue({
    kind: 'chapter',
    outlineNode: outline(),
    arcNode: null,
    loading: false,
    error: null,
    nameFor: (id: string | null) => (id ? `name:${id}` : null),
  } as PlanNodeView);
});

describe('PlanDrawer canon/thread facets (PH16/PH18)', () => {
  it('renders the canon refs the overlay ALREADY holds — no extra fetch', () => {
    const overlay = overlayWith({
      canon: 1,
      refs: [{ kind: 'canon', id: 'rule-9', line: 'Ha cannot fly before ch 40' }],
    });
    render(
      <PlanDrawer selectedId={NODE} kind="chapter" bookId="b" onClose={vi.fn()} overlay={overlay} />,
    );
    expect(screen.getByTestId('plan-drawer-canon-refs')).toBeTruthy();
    expect(screen.getByText('Ha cannot fly before ch 40')).toBeTruthy();
  });

  it('renders open-thread debt separately from canon', () => {
    const overlay = overlayWith({
      canon: 1,
      threads_open: 1,
      refs: [
        { kind: 'canon', id: 'rule-9', line: 'a canon rule' },
        { kind: 'thread', id: 'thr-2', line: 'who poisoned the well?' },
      ],
    });
    render(
      <PlanDrawer selectedId={NODE} kind="chapter" bookId="b" onClose={vi.fn()} overlay={overlay} />,
    );
    // each facet shows only its OWN kind — one ref each, not both in both.
    expect(screen.getByTestId('plan-drawer-canon-refs').textContent).toContain('a canon rule');
    expect(screen.getByTestId('plan-drawer-canon-refs').textContent).not.toContain('poisoned');
    expect(screen.getByTestId('plan-drawer-thread-refs').textContent).toContain('poisoned');
  });

  it('a ref DEEP-LINKS to its owning lens (PH18)', () => {
    const onOpenRef = vi.fn();
    const overlay = overlayWith({
      canon: 1,
      refs: [{ kind: 'canon', id: 'rule-9', line: 'a canon rule' }],
    });
    render(
      <PlanDrawer
        selectedId={NODE}
        kind="chapter"
        bookId="b"
        onClose={vi.fn()}
        overlay={overlay}
        onOpenRef={onOpenRef}
      />,
    );
    fireEvent.click(screen.getByTestId('plan-drawer-ref'));
    expect(onOpenRef).toHaveBeenCalledWith(
      { kind: 'canon', id: 'rule-9', line: 'a canon rule' },
      NODE,
    );
  });

  it('without onOpenRef the ref is plain text — never a link that does nothing', () => {
    const overlay = overlayWith({
      canon: 1,
      refs: [{ kind: 'canon', id: 'rule-9', line: 'a canon rule' }],
    });
    render(
      <PlanDrawer selectedId={NODE} kind="chapter" bookId="b" onClose={vi.fn()} overlay={overlay} />,
    );
    expect(screen.getByTestId('plan-drawer-ref').tagName).not.toBe('BUTTON');
  });

  it('a COUNT larger than the listed refs is explained, not silently short (OUT-5)', () => {
    // The overlay caps refs across the whole payload but keeps per-node counts EXACT. So a node can
    // legitimately say "3 canon" and list 1. Unexplained, that reads as a bug.
    const overlay = overlayWith(
      { canon: 3, refs: [{ kind: 'canon', id: 'rule-9', line: 'the only one that fit' }] },
      true,
    );
    render(
      <PlanDrawer selectedId={NODE} kind="chapter" bookId="b" onClose={vi.fn()} overlay={overlay} />,
    );
    const note = screen.getByTestId('plan-drawer-canon-refs-capped');
    expect(note.textContent).toContain('3 in total');
    expect(note.textContent).toContain('truncated');
  });

  it('no overlay ⇒ the facets say so honestly (not a crash, not a fake zero)', () => {
    render(<PlanDrawer selectedId={NODE} kind="chapter" bookId="b" onClose={vi.fn()} />);
    expect(screen.getByTestId('plan-drawer-section-canon')).toBeTruthy();
    expect(screen.getByTestId('plan-drawer-section-threads')).toBeTruthy();
  });
});
