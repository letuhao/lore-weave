import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// C6 hunk-review — a replace_selection proposal is diffed against the live editor
// selection (captured at mount) and offered as per-hunk accept/reject. Accept-all
// writes the proposal verbatim; a partial accept writes the reconstructed merge;
// reject-all routes to Dismiss. insert_at_cursor keeps the whole-text card.

const submitToolResult = vi.fn().mockResolvedValue('');
const replaceSelection = vi.fn(() => true);
const insertAtCursor = vi.fn(() => true);
let selection: { from: number; to: number; empty: boolean; text: string } | null;

vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../context/editorBridge', () => ({
  getEditorTarget: () => ({
    bookId: 'b1',
    chapterId: 'ch1',
    handle: {
      getSelection: () => selection,
      replaceSelection: (...a: unknown[]) => replaceSelection(...a),
      insertAtCursor: (...a: unknown[]) => insertAtCursor(...a),
    },
  }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

import { ProposeEditCard } from '../ProposeEditCard';
import type { ToolCallRecord } from '../../types';

function record(args: Record<string, unknown>): ToolCallRecord {
  return { tool: 'propose_edit', ok: true, pending: true, runId: 'r1', toolCallId: 'c1', args };
}

describe('ProposeEditCard — hunk review', () => {
  beforeEach(() => {
    submitToolResult.mockClear();
    replaceSelection.mockClear();
    insertAtCursor.mockClear();
    selection = { from: 0, to: 10, empty: false, text: 'A. B. C.' };
  });

  it('renders per-hunk diff for a replace_selection rewrite', () => {
    render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'X. B. Y.' })} />);
    expect(screen.getByTestId('propose-hunks')).toBeInTheDocument();
    // A→X and C→Y are two hunks; the unchanged B is context, not a hunk.
    expect(screen.getByTestId('propose-hunk-0')).toBeInTheDocument();
    expect(screen.getByTestId('propose-hunk-1')).toBeInTheDocument();
    expect(screen.queryByTestId('propose-hunk-2')).not.toBeInTheDocument();
  });

  it('accept-all Apply writes the proposal verbatim + resumes applied', async () => {
    render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'X. B. Y.' })} />);
    fireEvent.click(screen.getByText('propose.apply'));
    await waitFor(() => expect(replaceSelection).toHaveBeenCalledTimes(1));
    // verbatim proposal (no sentence-normalization on the happy path)
    expect(replaceSelection.mock.calls[0][0]).toBe('X. B. Y.');
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied', 'X. B. Y.'),
    );
  });

  it('a partial accept writes the reconstructed merge', async () => {
    render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'X. B. Y.' })} />);
    // reject the second hunk (C→Y) — keep C
    const h1 = screen.getByTestId('propose-hunk-1').querySelector('input')!;
    fireEvent.click(h1);
    fireEvent.click(screen.getByText('propose.apply_n'));
    await waitFor(() => expect(replaceSelection).toHaveBeenCalledTimes(1));
    expect(replaceSelection.mock.calls[0][0]).toBe('X. B. C.');
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied', 'X. B. C.'),
    );
  });

  it('aborts a partial merge if the live selection drifted from the mount snapshot', async () => {
    render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'X. B. Y.' })} />);
    fireEvent.click(screen.getByTestId('propose-hunk-1').querySelector('input')!); // partial
    // user moved the selection since the card mounted
    selection = { from: 20, to: 30, empty: false, text: 'totally different span' };
    fireEvent.click(screen.getByText('propose.apply_n'));
    // no stale-range splice; run stays suspended (buttons remain) for a re-ask
    await waitFor(() => expect(screen.getByText('propose.apply_n')).toBeInTheDocument());
    expect(replaceSelection).not.toHaveBeenCalled();
    expect(submitToolResult).not.toHaveBeenCalled();
  });

  it('rejecting every hunk routes Apply to Dismiss (no write)', async () => {
    render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'X. B. Y.' })} />);
    fireEvent.click(screen.getByTestId('propose-hunk-0').querySelector('input')!);
    fireEvent.click(screen.getByTestId('propose-hunk-1').querySelector('input')!);
    fireEvent.click(screen.getByText('propose.keep_original'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'dismissed'));
    expect(replaceSelection).not.toHaveBeenCalled();
  });

  it('insert_at_cursor keeps the whole-text card (no hunks)', async () => {
    render(<ProposeEditCard record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })} />);
    expect(screen.queryByTestId('propose-hunks')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('propose.apply'));
    await waitFor(() => expect(insertAtCursor).toHaveBeenCalledTimes(1));
    expect(insertAtCursor.mock.calls[0][0]).toBe('New paragraph.');
  });

  it('replace_selection with no live selection falls back to the whole-text card', async () => {
    selection = { from: 5, to: 5, empty: true, text: '' };
    render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'Whole rewrite.' })} />);
    expect(screen.queryByTestId('propose-hunks')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('propose.apply'));
    await waitFor(() => expect(replaceSelection).toHaveBeenCalledWith('Whole rewrite.', expect.anything()));
  });
});
