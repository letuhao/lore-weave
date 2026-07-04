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
let targetChapterId = 'ch1';
const toastError = vi.fn();
// #16 P1 — undefined by default (legacy path: no hoist, Apply calls target.handle.* directly,
// same as before). Tests that need the Studio hoist-preferred path set this to a vi.fn().
let applyProposedEdit: ReturnType<typeof vi.fn> | undefined;

vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));
vi.mock('../../context/editorBridge', () => ({
  getEditorTarget: () => ({
    bookId: 'b1',
    chapterId: targetChapterId,
    handle: {
      getSelection: () => selection,
      replaceSelection: (...a: unknown[]) => replaceSelection(...a),
      insertAtCursor: (...a: unknown[]) => insertAtCursor(...a),
    },
    applyProposedEdit,
  }),
}));
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a) } }));

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
    toastError.mockClear();
    selection = { from: 0, to: 10, empty: false, text: 'A. B. C.' };
    targetChapterId = 'ch1';
    applyProposedEdit = undefined;
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

  // /review-impl HIGH — no caller ever passes the `chapterId` prop (AssistantMessage renders
  // `<ProposeEditCard record={tc} />` bare), so the cross-chapter guard was dead in production:
  // on a surface where the editor stays mounted across a chapter switch (Studio's dock), Apply
  // would silently splice a stale proposal into whatever chapter is CURRENTLY open. The card now
  // self-derives the target chapter from the live editor bridge at mount instead.
  describe('cross-chapter guard (self-derived, no chapterId prop from the caller)', () => {
    it('blocks Apply if the open chapter changed since this card mounted', async () => {
      // Card mounts while chapter 'ch1' is open (the chapter the proposal was generated for).
      render(<ProposeEditCard record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })} />);
      // User navigates to a different chapter in the studio manuscript tree before clicking Apply.
      targetChapterId = 'ch2';
      fireEvent.click(screen.getByText('propose.apply'));
      // i18n isn't initialized in this test env — useTranslation resolves to the raw key.
      await waitFor(() => expect(toastError).toHaveBeenCalledWith('propose.wrong_chapter'));
      expect(insertAtCursor).not.toHaveBeenCalled();
      expect(submitToolResult).not.toHaveBeenCalled();
      // The run stays suspended — buttons remain for a re-ask, not silently resolved.
      expect(screen.getByText('propose.apply')).toBeInTheDocument();
    });

    it('applies normally when the chapter is unchanged at Apply time', async () => {
      render(<ProposeEditCard record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })} />);
      fireEvent.click(screen.getByText('propose.apply'));
      await waitFor(() => expect(insertAtCursor).toHaveBeenCalledTimes(1));
      expect(toastError).not.toHaveBeenCalled();
    });

    it('an explicit chapterId prop still overrides the self-derived snapshot', async () => {
      // A future caller that resolves its own canonical chapterId should win over the bridge.
      render(
        <ProposeEditCard
          record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })}
          chapterId="ch-explicit"
        />,
      );
      // Live bridge target is 'ch1' — mismatched against the explicit prop — Apply must block.
      fireEvent.click(screen.getByText('propose.apply'));
      await waitFor(() => expect(toastError).toHaveBeenCalledWith('propose.wrong_chapter'));
      expect(insertAtCursor).not.toHaveBeenCalled();
    });
  });

  // #16 P1 (Lane C — spec 09) — when the registrant (Studio's EditorPanel) supplies a hoist-owned
  // applyProposedEdit action, Apply must call it INSTEAD of the raw handle. Legacy (no hoist,
  // applyProposedEdit undefined) keeps calling target.handle.* directly — covered by every test
  // above, which never set applyProposedEdit.
  describe('hoist-preferred apply (#16 P1)', () => {
    it('calls applyProposedEdit instead of target.handle.insertAtCursor when supplied', async () => {
      applyProposedEdit = vi.fn(() => true);
      render(<ProposeEditCard record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })} />);
      fireEvent.click(screen.getByText('propose.apply'));
      await waitFor(() => expect(applyProposedEdit).toHaveBeenCalledWith(
        expect.objectContaining({ operation: 'insert_at_cursor', text: 'New paragraph.' }),
      ));
      expect(insertAtCursor).not.toHaveBeenCalled();
      await waitFor(() =>
        expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'applied', 'New paragraph.'));
    });

    it('calls applyProposedEdit instead of target.handle.replaceSelection when supplied', async () => {
      applyProposedEdit = vi.fn(() => true);
      render(<ProposeEditCard record={record({ operation: 'replace_selection', text: 'X. B. Y.' })} />);
      fireEvent.click(screen.getByText('propose.apply'));
      await waitFor(() => expect(applyProposedEdit).toHaveBeenCalledWith(
        expect.objectContaining({ operation: 'replace_selection', text: 'X. B. Y.' }),
      ));
      expect(replaceSelection).not.toHaveBeenCalled();
    });

    it('a false return from applyProposedEdit surfaces the same failure toast as the raw handle', async () => {
      applyProposedEdit = vi.fn(() => false);
      render(<ProposeEditCard record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })} />);
      fireEvent.click(screen.getByText('propose.apply'));
      await waitFor(() => expect(toastError).toHaveBeenCalledWith('propose.apply_failed'));
      expect(submitToolResult).not.toHaveBeenCalled();
    });

    // /review-impl coverage gap — the chapter-mismatch guard (mountChapterId) runs BEFORE the
    // hoist-vs-raw-handle branch in code, but nothing proved the combination: a hoist action
    // being configured must not bypass the guard.
    it('the cross-chapter guard still blocks Apply even when a hoist applyProposedEdit is configured', async () => {
      applyProposedEdit = vi.fn(() => true);
      render(<ProposeEditCard record={record({ operation: 'insert_at_cursor', text: 'New paragraph.' })} />);
      targetChapterId = 'ch2'; // chapter switched after mount, before Apply
      fireEvent.click(screen.getByText('propose.apply'));
      await waitFor(() => expect(toastError).toHaveBeenCalledWith('propose.wrong_chapter'));
      expect(applyProposedEdit).not.toHaveBeenCalled();
      expect(submitToolResult).not.toHaveBeenCalled();
    });
  });
});
