import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import type { EntityKind } from '../../types';

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const hookMocks = vi.hoisted(() => ({
  resolve: vi.fn(),
  state: { items: [] as unknown[], total: 0, isLoading: false, error: null as unknown },
}));
vi.mock('../../hooks/useUnknownReview', () => ({
  useUnknownReview: () => ({
    items: hookMocks.state.items,
    total: hookMocks.state.total,
    isLoading: hookMocks.state.isLoading,
    error: hookMocks.state.error,
    refetch: vi.fn(),
    resolve: hookMocks.resolve,
  }),
}));

import { UnknownEntitiesPanel } from '../UnknownEntitiesPanel';

const k = (kind_id: string, code: string, name: string, is_hidden = false, sort_order = 1) =>
  ({ kind_id, code, name, icon: '◆', is_hidden, sort_order } as unknown as EntityKind);

const KINDS: EntityKind[] = [
  k('k-loc', 'location', 'Location', false, 1),
  k('k-org', 'organization', 'Organization', false, 2),
  k('k-unknown', 'unknown', 'Unknown', true, 99),
];

const ITEMS = [
  { entity_id: 'e1', name: '哪吒', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z' },
  { entity_id: 'e2', name: '楊戩', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z' },
  { entity_id: 'e3', name: '番天印', source_kind_code: null, status: 'draft', created_at: '2026-06-04T00:00:00Z' },
];

function renderPanel() {
  return render(<UnknownEntitiesPanel bookId="book-1" kinds={KINDS} onClose={vi.fn()} />);
}

beforeEach(() => {
  hookMocks.resolve.mockReset().mockResolvedValue({ action: 'reassigned', name: 'x' });
  Object.values(toastMocks).forEach((m) => m.mockReset());
  hookMocks.state = { items: ITEMS, total: 3, isLoading: false, error: null };
});

describe('UnknownEntitiesPanel', () => {
  it('renders the queue with source-code badges and the no-source-code marker', () => {
    renderPanel();
    expect(screen.getByText('哪吒')).toBeInTheDocument();
    expect(screen.getByText('番天印')).toBeInTheDocument();
    expect(screen.getAllByText('unknown.arrived_as')).toHaveLength(2);
    expect(screen.getByText('unknown.no_source_code')).toBeInTheDocument();
  });

  it('shows a scope_label badge only for entities that have one set', () => {
    hookMocks.state = {
      items: [
        { entity_id: 'e1', name: '哪吒', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z', scope_label: 'World A' },
        { entity_id: 'e2', name: '楊戩', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z' },
      ],
      total: 2,
      isLoading: false,
      error: null,
    };
    renderPanel();
    expect(screen.getByText('World A')).toBeInTheDocument();
  });

  it('shows the empty state when there is nothing to review', () => {
    hookMocks.state = { items: [], total: 0, isLoading: false, error: null };
    renderPanel();
    expect(screen.getByText('unknown.empty_title')).toBeInTheDocument();
  });

  it('shows the truncation hint when the queue is capped below the true total', () => {
    hookMocks.state = { items: ITEMS, total: 503, isLoading: false, error: null };
    renderPanel();
    expect(screen.getByText('unknown.truncated')).toBeInTheDocument();
  });

  it('does NOT show the truncation hint when everything fits', () => {
    renderPanel(); // total === items.length === 3
    expect(screen.queryByText('unknown.truncated')).toBeNull();
  });

  it('excludes the hidden "unknown" kind from the reassign targets', () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e1'));
    const select = screen.getByTestId('resolve-kind-select');
    const opts = within(select).getAllByRole('option').map((o) => o.getAttribute('value'));
    expect(opts).toEqual(['k-loc', 'k-org']); // no 'k-unknown'
  });

  it('resolving with merge-all (default) requests existing+applyAll for the entity', async () => {
    hookMocks.resolve.mockResolvedValue({ action: 'merged', count: 2, code: 'faction' });
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e1'));
    expect(screen.getByTestId('resolve-merge-all')).toBeChecked();
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(hookMocks.resolve).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: 'e1' }),
      { strategy: 'existing', kindId: 'k-loc', applyAll: true },
    ));
    expect(toastMocks.success).toHaveBeenCalledWith('unknown.toast_merged');
  });

  it('unchecking merge-all requests existing+single', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e1'));
    fireEvent.click(screen.getByTestId('resolve-merge-all')); // uncheck
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(hookMocks.resolve).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: 'e1' }),
      { strategy: 'existing', kindId: 'k-loc', applyAll: false },
    ));
  });

  it('an entity with no source code has no merge option (applyAll forced false)', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e3'));
    expect(screen.queryByTestId('resolve-merge-all')).toBeNull();
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(hookMocks.resolve).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: 'e3' }),
      { strategy: 'existing', kindId: 'k-loc', applyAll: false },
    ));
  });

  it('the "new kind" strategy requests strategy=new with the typed code/name', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e3'));
    fireEvent.click(screen.getByTestId('resolve-strategy-new'));
    fireEvent.change(screen.getByTestId('resolve-new-name'), { target: { value: 'Faction' } });
    fireEvent.change(screen.getByTestId('resolve-new-code'), { target: { value: 'faction' } });
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(hookMocks.resolve).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: 'e3' }),
      { strategy: 'new', code: 'faction', name: 'Faction', applyAll: false },
    ));
  });

  it('on resolve failure keeps the modal open with an inline error and no success toast', async () => {
    hookMocks.resolve.mockRejectedValue(new Error('reassign boom'));
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e1'));
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(screen.getByText('reassign boom')).toBeInTheDocument());
    // modal still mounted (apply button present), no success toast fired
    expect(screen.getByTestId('resolve-apply')).toBeInTheDocument();
    expect(toastMocks.success).not.toHaveBeenCalled();
  });

  it('rejects an invalid new-kind code without calling resolve', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('unknown-resolve-e3'));
    fireEvent.click(screen.getByTestId('resolve-strategy-new'));
    fireEvent.change(screen.getByTestId('resolve-new-name'), { target: { value: 'Bad' } });
    fireEvent.change(screen.getByTestId('resolve-new-code'), { target: { value: 'Bad Code!' } });
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(screen.getByText('unknown.err_code_format')).toBeInTheDocument());
    expect(hookMocks.resolve).not.toHaveBeenCalled();
  });
});
