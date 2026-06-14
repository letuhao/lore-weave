import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { Work } from '@/features/composition/types';
import { buildWorldTree, type WorldBookRef } from '../../lib/livingWorldTree';
import { LivingWorldTree } from '../LivingWorldTree';

// C28 — the living-world tree renders the canon trunk + dị bản branches (reusing
// GraphCanvas) and navigates into a Work on click via an EXPLICIT handler.

const navigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});
// A minimal interpolating t() (real i18next substitutes {{var}}), so count /
// branch_point labels render their values like in the app.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => {
      let s = (o?.defaultValue as string | undefined) ?? k;
      if (o) {
        for (const [key, val] of Object.entries(o)) {
          if (key === 'defaultValue') continue;
          s = s.replace(new RegExp(`{{\\s*${key}\\s*}}`, 'g'), String(val));
        }
      }
      return s;
    },
  }),
}));

// Drive the component off a real built tree, with the hook stubbed to return it.
const hookState = { tree: emptyTree(), isLoading: false, isError: false, error: null as Error | null, isEmpty: false };
vi.mock('../../hooks/useLivingWorld', () => ({
  useLivingWorld: () => hookState,
}));

function emptyTree() {
  return buildWorldTree([], {});
}
function work(p: Partial<Work> & { id: string; book_id: string }): Work {
  return {
    project_id: p.project_id ?? p.id, user_id: 'u1', book_id: p.book_id, active_template_id: null,
    status: 'active', settings: {}, version: 1, id: p.id,
    source_work_id: p.source_work_id ?? null, branch_point: p.branch_point ?? null,
  };
}
const books: WorldBookRef[] = [{ bookId: 'bookA', title: '万古神帝' }];

function renderTree() {
  return render(
    <MemoryRouter initialEntries={['/worlds/w1']}>
      <Routes>
        <Route path="/worlds/:worldId" element={<LivingWorldTree worldId="w1" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  hookState.tree = emptyTree();
  hookState.isLoading = false;
  hookState.isError = false;
  hookState.error = null;
  hookState.isEmpty = false;
});

describe('LivingWorldTree', () => {
  it('renders the canon trunk + ≥2 dị bản branches', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 2 });
    const d2 = work({ id: 'w-d2', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 4 });
    hookState.tree = buildWorldTree(books, { bookA: [canon, d1, d2] });

    renderTree();
    expect(screen.getByTestId('living-world-tree')).toBeInTheDocument();
    // 3 nodes (1 canon + 2 branches).
    expect(screen.getAllByTestId('world-tree-node')).toHaveLength(3);
    // 2 branch connectors.
    expect(screen.getAllByTestId('branch-edge')).toHaveLength(2);
    // canon + 2 branch badges.
    const canonNode = document.querySelector('[data-work="w-canon"][data-canon="true"]');
    expect(canonNode).toBeTruthy();
    expect(document.querySelectorAll('[data-canon="false"]')).toHaveLength(2);
    // counts line reflects EXACTLY 1 canon · 2 branches (full interpolated
    // string — a canon↔branch transposition would fail this).
    expect(screen.getByTestId('living-world-counts').textContent).toBe('1 canon · 2 dị bản branches');
  });

  it('click a node → navigates into that Work’s book (explicit handler)', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookB', source_work_id: 'w-canon', branch_point: 2 });
    hookState.tree = buildWorldTree(
      [{ bookId: 'bookA', title: 'Canon' }, { bookId: 'bookB', title: 'Branch' }],
      { bookA: [canon], bookB: [d1] },
    );
    renderTree();
    // A click = a pointer press + release with no travel (GraphCanvas → onNodeClick).
    const branchBody = document.querySelector('[data-work="w-d1"] [data-testid="world-tree-node-body"]')!;
    fireEvent.pointerDown(branchBody);
    fireEvent.pointerUp(document.querySelector('[data-testid="living-world-svg"]')!);
    // The `?work=` selector disambiguates which Work to open (canon + dị bản
    // share a book_id under COW) so the click lands in THIS branch's studio.
    expect(navigate).toHaveBeenCalledWith('/books/bookB?work=w-d1');
  });

  it('the canon trunk navigates with its own ?work= selector too', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 2 });
    hookState.tree = buildWorldTree(books, { bookA: [canon, d1] });
    renderTree();
    const canonBody = document.querySelector('[data-work="w-canon"] [data-testid="world-tree-node-body"]')!;
    fireEvent.keyDown(canonBody, { key: 'Enter' });
    expect(navigate).toHaveBeenCalledWith('/books/bookA?work=w-canon');
  });

  it('keyboard Enter on a node activates navigation (explicit, not useEffect)', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    hookState.tree = buildWorldTree(books, { bookA: [canon] });
    renderTree();
    const body = document.querySelector('[data-work="w-canon"] [data-testid="world-tree-node-body"]')!;
    fireEvent.keyDown(body, { key: 'Enter' });
    expect(navigate).toHaveBeenCalledWith('/books/bookA?work=w-canon');
  });

  it('a branch node shows its branch_point metadata', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 3 });
    hookState.tree = buildWorldTree(books, { bookA: [canon, d1] });
    renderTree();
    const bp = screen.getByTestId('world-tree-node-branchpoint');
    // branch_point 3 → "branches at ch. 4" (chapter-level, 1-indexed display).
    expect(bp.textContent).toContain('4');
  });

  it('is READ-ONLY — no edit/delete affordance on the tree', () => {
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    hookState.tree = buildWorldTree(books, { bookA: [canon] });
    renderTree();
    // No edit/delete/save buttons anywhere in the tree.
    const buttons = Array.from(document.querySelectorAll('button')).map((b) => (b.getAttribute('aria-label') ?? b.textContent ?? '').toLowerCase());
    expect(buttons.some((l) => /edit|delete|remove|save/.test(l))).toBe(false);
  });

  it('renders the empty state when the world has no works', () => {
    hookState.isEmpty = true;
    renderTree();
    expect(screen.getByTestId('living-world-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('living-world-tree')).not.toBeInTheDocument();
  });

  it('renders the loading and error states', () => {
    hookState.isLoading = true;
    const { rerender } = renderTree();
    expect(screen.getByTestId('living-world-loading')).toBeInTheDocument();

    hookState.isLoading = false;
    hookState.isError = true;
    hookState.error = new Error('boom');
    rerender(
      <MemoryRouter initialEntries={['/worlds/w1']}>
        <Routes>
          <Route path="/worlds/:worldId" element={<LivingWorldTree worldId="w1" />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('living-world-error')).toBeInTheDocument();
  });
});
