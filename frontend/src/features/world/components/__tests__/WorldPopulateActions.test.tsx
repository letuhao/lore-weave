import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const navigateMock = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}));

const livingWorldMock = vi.fn();
vi.mock('../../hooks/useLivingWorld', () => ({
  useLivingWorld: () => livingWorldMock(),
}));

// Stub the modal so we only assert it opens (its internals are covered separately).
vi.mock('../AddBookToWorldModal', () => ({
  AddBookToWorldModal: ({ open }: { open: boolean }) =>
    open ? <div data-testid="add-book-modal-open" /> : null,
}));

import { WorldPopulateActions } from '../WorldPopulateActions';

function canonNode(id: string, bookId: string, bookTitle: string) {
  return { id, bookId, bookTitle, isCanon: true, work: {}, branchPoint: null, parentId: null, depth: 0, orphanSource: false };
}
function tree(nodes: unknown[]) {
  return {
    tree: { nodes, edges: [], trunkCount: nodes.length, branchCount: 0 },
    isLoading: false, isError: false, error: null, isEmpty: nodes.length === 0,
  };
}

beforeEach(() => {
  navigateMock.mockReset();
  livingWorldMock.mockReset();
});

describe('WorldPopulateActions (W5/G1)', () => {
  it('opens the add-book modal from the CTA', () => {
    livingWorldMock.mockReturnValue(tree([]));
    render(<WorldPopulateActions worldId="w1" />);
    fireEvent.click(screen.getByTestId('world-add-book'));
    expect(screen.getByTestId('add-book-modal-open')).toBeInTheDocument();
  });

  it('disables "create a what-if" when the world has no canon work', () => {
    livingWorldMock.mockReturnValue(tree([]));
    render(<WorldPopulateActions worldId="w1" />);
    expect(screen.getByTestId('world-create-whatif')).toBeDisabled();
  });

  it('routes straight to the canon studio when there is exactly one canon', () => {
    livingWorldMock.mockReturnValue(tree([canonNode('wk1', 'bk1', 'Canon One')]));
    render(<WorldPopulateActions worldId="w1" />);
    fireEvent.click(screen.getByTestId('world-create-whatif'));
    expect(navigateMock).toHaveBeenCalledWith('/books/bk1?work=wk1');
    // no picker for a single source.
    expect(screen.queryByTestId('world-whatif-picker')).toBeNull();
  });

  it('opens a source picker when there is more than one canon, then routes on pick', () => {
    livingWorldMock.mockReturnValue(
      tree([canonNode('wk1', 'bk1', 'Canon One'), canonNode('wk2', 'bk2', 'Canon Two')]),
    );
    render(<WorldPopulateActions worldId="w1" />);
    fireEvent.click(screen.getByTestId('world-create-whatif'));
    // picker opens instead of navigating.
    expect(navigateMock).not.toHaveBeenCalled();
    const picker = screen.getByTestId('world-whatif-picker');
    fireEvent.click(within(picker).getByText('Canon Two'));
    expect(navigateMock).toHaveBeenCalledWith('/books/bk2?work=wk2');
  });
});
