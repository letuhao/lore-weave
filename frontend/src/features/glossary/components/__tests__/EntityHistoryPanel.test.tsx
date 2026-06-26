import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { EntityRevisionSummary } from '../../types';

// VG-3 — EntityHistoryPanel renders the revision list and drives restore-via-confirm.

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const hookMocks = vi.hoisted(() => ({
  restore: vi.fn(),
  revisions: [] as EntityRevisionSummary[],
  detail: null as unknown,
  error: null as unknown,
}));
vi.mock('../../hooks/useEntityRevisions', () => ({
  useEntityRevisions: () => ({
    revisions: hookMocks.revisions,
    isLoading: false,
    error: hookMocks.error,
    refetch: vi.fn(),
    restore: hookMocks.restore,
  }),
  useEntityRevisionDetail: () => ({ detail: hookMocks.detail, isLoading: false }),
}));

import { EntityHistoryPanel } from '../EntityHistoryPanel';

const rev = (n: number, op = 'updated', actor = 'user'): EntityRevisionSummary => ({
  revision_id: `r${n}`,
  revision_num: n,
  op,
  actor_type: actor,
  created_at: '2026-06-07T00:00:00Z',
});

function renderPanel(onRestored = vi.fn()) {
  render(<EntityHistoryPanel bookId="b1" entityId="e1" onRestored={onRestored} onClose={vi.fn()} />);
  return { onRestored };
}

beforeEach(() => {
  hookMocks.restore.mockReset().mockResolvedValue(undefined);
  toastMocks.success.mockReset();
  hookMocks.revisions = [];
  hookMocks.detail = null;
  hookMocks.error = null;
});

describe('EntityHistoryPanel', () => {
  it('lists revisions newest-first as served', () => {
    hookMocks.revisions = [rev(3), rev(2), rev(1, 'baseline', 'system')];
    renderPanel();
    expect(screen.getByText('#3')).toBeTruthy();
    expect(screen.getByText('#2')).toBeTruthy();
    expect(screen.getByText('#1')).toBeTruthy();
  });

  it('shows the empty state when there are no revisions', () => {
    renderPanel();
    expect(screen.getByText('history.empty')).toBeTruthy();
  });

  it('shows a distinct error state on fetch failure (not the empty state)', () => {
    hookMocks.error = new Error('boom');
    renderPanel();
    expect(screen.getByText('history.error')).toBeTruthy();
    expect(screen.queryByText('history.empty')).toBeNull(); // must NOT read as "no history"
  });

  it('View renders the revision full snapshot (name, translation, status)', () => {
    hookMocks.revisions = [rev(2)];
    hookMocks.detail = {
      ...rev(2),
      snapshot: {
        status: 'active',
        tags: ['hero'],
        attributes: [
          {
            code: 'name',
            name: 'Name',
            original_value: '提拉米',
            translations: [{ language_code: 'vi', value: 'Tirami', confidence: 'verified' }],
            evidences: [],
          },
        ],
        chapter_links: [],
      },
    };
    renderPanel();
    fireEvent.click(screen.getByText('history.view'));
    expect(screen.getByText(/提拉米/)).toBeTruthy();
    expect(screen.getByText(/Tirami/)).toBeTruthy();
    expect(screen.getByText(/active/)).toBeTruthy();
  });

  it('embedded mode drops the overlay header/close (tab-content variant) but still lists revisions', () => {
    hookMocks.revisions = [rev(2)];
    // No onClose passed — it is optional when embedded (host modal owns chrome).
    render(<EntityHistoryPanel bookId="b1" entityId="e1" embedded onRestored={vi.fn()} />);
    expect(screen.getByText('#2')).toBeTruthy(); // list still renders
    expect(screen.queryByText('history.title')).toBeNull(); // no overlay title
    expect(screen.queryByLabelText('history.close')).toBeNull(); // no overlay close button
  });

  it('restore requires confirm, then calls restore + onRestored', async () => {
    hookMocks.revisions = [rev(1)];
    const { onRestored } = renderPanel();

    // The per-row Restore opens the confirm dialog (no API call yet).
    fireEvent.click(screen.getAllByText('history.restore')[0]);
    expect(screen.getByText('history.restore_confirm_title')).toBeTruthy();
    expect(hookMocks.restore).not.toHaveBeenCalled();

    // Confirm → restore the revision + notify the editor.
    const restoreButtons = screen.getAllByText('history.restore');
    fireEvent.click(restoreButtons[restoreButtons.length - 1]);
    await waitFor(() => expect(hookMocks.restore).toHaveBeenCalledWith('r1'));
    expect(onRestored).toHaveBeenCalled();
  });
});
