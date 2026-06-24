import { describe, it, expect } from 'vitest';
import { buildWorldTree, layoutWorldTree, type WorldBookRef } from '../livingWorldTree';
import type { Work } from '@/features/composition/types';

// C28 — the living-world tree spine: canon TRUNK + dị bản BRANCHES resolved via
// C23's `source_work_id → id` chain, anchored at chapter-level `branch_point`
// (G3), among ONLY the world's collected Works (no cross-world bleed).

function work(partial: Partial<Work> & { id: string; book_id: string }): Work {
  return {
    project_id: partial.project_id ?? partial.id,
    user_id: 'u1',
    book_id: partial.book_id,
    active_template_id: null,
    status: 'active',
    settings: {},
    version: 1,
    id: partial.id,
    source_work_id: partial.source_work_id ?? null,
    branch_point: partial.branch_point ?? null,
  };
}

const books: WorldBookRef[] = [{ bookId: 'bookA', title: '万古神帝' }];

describe('buildWorldTree', () => {
  it('canon-only book → a single trunk node, no branches', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const tree = buildWorldTree(books, { bookA: [canon] });
    expect(tree.trunkCount).toBe(1);
    expect(tree.branchCount).toBe(0);
    expect(tree.edges).toHaveLength(0);
    expect(tree.nodes[0].isCanon).toBe(true);
    expect(tree.nodes[0].depth).toBe(0);
  });

  it('canon + 1 derivative → trunk + 1 branch, parent resolved via source_work_id→id', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const deriv = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 3 });
    const tree = buildWorldTree(books, { bookA: [canon, deriv] });
    expect(tree.trunkCount).toBe(1);
    expect(tree.branchCount).toBe(1);
    const branch = tree.nodes.find((n) => n.id === 'w-d1')!;
    expect(branch.isCanon).toBe(false);
    expect(branch.parentId).toBe('w-canon');
    expect(branch.branchPoint).toBe(3); // anchored at its branch_point (chapter-level, G3)
    expect(branch.depth).toBe(1);
    expect(tree.edges).toEqual([
      { id: 'w-canon->w-d1', from: 'w-canon', to: 'w-d1', branchPoint: 3 },
    ]);
  });

  it('canon + 2 derivatives → trunk + ≥2 branches (the M6 acceptance shape)', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 3 });
    const d2 = work({ id: 'w-d2', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 5 });
    const tree = buildWorldTree(books, { bookA: [canon, d1, d2] });
    expect(tree.trunkCount).toBe(1);
    expect(tree.branchCount).toBe(2);
    expect(tree.edges).toHaveLength(2);
    const bps = tree.nodes.filter((n) => !n.isCanon).map((n) => n.branchPoint).sort();
    expect(bps).toEqual([3, 5]);
  });

  it('2nd-degree derivative (a dị bản of a dị bản) chains to depth 2', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 3 });
    const d2 = work({ id: 'w-d2', book_id: 'bookA', source_work_id: 'w-d1', branch_point: 6 });
    const tree = buildWorldTree(books, { bookA: [canon, d1, d2] });
    const grand = tree.nodes.find((n) => n.id === 'w-d2')!;
    expect(grand.parentId).toBe('w-d1');
    expect(grand.depth).toBe(2);
    expect(tree.edges.map((e) => e.id).sort()).toEqual(['w-canon->w-d1', 'w-d1->w-d2']);
  });

  it('does NOT let another world’s branches bleed in (only collected Works are joined)', () => {
    // A derivative whose source Work is NOT among the world's collected Works is
    // an orphan — rendered at the root (never silently dropped), but NOT joined
    // to a foreign parent.
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const foreignDeriv = work({ id: 'w-foreign', book_id: 'bookA', source_work_id: 'w-OTHER-WORLD', branch_point: 2 });
    const tree = buildWorldTree(books, { bookA: [canon, foreignDeriv] });
    const orphan = tree.nodes.find((n) => n.id === 'w-foreign')!;
    expect(orphan.orphanSource).toBe(true);
    expect(orphan.parentId).toBeNull(); // not joined to the foreign source
    // No edge references the foreign (cross-world) source.
    expect(tree.edges.some((e) => e.from === 'w-OTHER-WORLD')).toBe(false);
  });

  it('excludes a lazy null-project pending Work (no spine identity)', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    // A pending Work has a null project_id AND no surrogate id in some shapes;
    // model it as having neither key.
    const pending = { ...work({ id: 'x', book_id: 'bookA' }), id: null, project_id: null } as Work;
    const tree = buildWorldTree(books, { bookA: [canon, pending] });
    expect(tree.nodes).toHaveLength(1);
    expect(tree.nodes[0].id).toBe('w-canon');
  });

  it('de-duplicates a Work listed twice (e.g. as work AND candidate)', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const tree = buildWorldTree(books, { bookA: [canon, canon] });
    expect(tree.nodes).toHaveLength(1);
  });
});

describe('layoutWorldTree', () => {
  it('places the trunk left and branches to its right by depth', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 3 });
    const tree = buildWorldTree(books, { bookA: [canon, d1] });
    const pos = layoutWorldTree(tree);
    expect(pos['w-canon'].x).toBeLessThan(pos['w-d1'].x); // branch is to the right
    // every node gets a position
    expect(Object.keys(pos).sort()).toEqual(['w-canon', 'w-d1']);
  });
});
