import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TurnCheckpoints } from '../TurnCheckpoints';
import type { TurnCheckpoint } from '../../hooks/useTurnCheckpoints';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function cp(over: Partial<TurnCheckpoint> = {}): TurnCheckpoint {
  return { id: 'k1', chapterId: 'c1', preRevisionId: 'rev-A', at: 1, snippet: 'Once', count: 1, kind: 'insert', ...over };
}

describe('TurnCheckpoints (RAID C6)', () => {
  it('renders nothing when there are no checkpoints', () => {
    const { container } = render(<TurnCheckpoints checkpoints={[]} chapterId="c1" onRestore={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a row per checkpoint with the fold count', () => {
    render(<TurnCheckpoints checkpoints={[cp({ count: 3 })]} chapterId="c1" onRestore={vi.fn()} />);
    expect(screen.getByTestId('turn-checkpoints')).toBeInTheDocument();
    expect(screen.getByText('×3')).toBeInTheDocument();
  });

  it('renders ONLY the current chapter\'s checkpoints, hiding stale other-chapter rows (MED-1)', () => {
    const rows = [
      cp({ id: 'y1', chapterId: 'c2', snippet: 'other-chapter' }),
      cp({ id: 'x1', chapterId: 'c1', snippet: 'this-chapter' }),
    ];
    render(<TurnCheckpoints checkpoints={rows} chapterId="c1" onRestore={vi.fn()} />);
    expect(screen.getAllByTestId('turn-checkpoint-row')).toHaveLength(1);
    expect(screen.getByText(/this-chapter/)).toBeInTheDocument();
    expect(screen.queryByText(/other-chapter/)).not.toBeInTheDocument();
  });

  it('renders nothing when every checkpoint belongs to a different chapter (MED-1)', () => {
    const { container } = render(
      <TurnCheckpoints checkpoints={[cp({ chapterId: 'c2' })]} chapterId="c1" onRestore={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('disables Restore when there is no pre-revision', () => {
    render(<TurnCheckpoints checkpoints={[cp({ preRevisionId: null })]} chapterId="c1" onRestore={vi.fn()} />);
    expect(screen.getByTestId('turn-checkpoint-restore')).toBeDisabled();
  });

  it('confirming Restore invokes onRestore with the checkpoint', async () => {
    const onRestore = vi.fn().mockResolvedValue(undefined);
    render(<TurnCheckpoints checkpoints={[cp()]} chapterId="c1" onRestore={onRestore} />);
    fireEvent.click(screen.getByTestId('turn-checkpoint-restore'));
    // ConfirmDialog renders the confirm button; click it (there are 2 "Restore"
    // labels now — the row + the dialog confirm — pick the dialog's).
    const confirmButtons = await screen.findAllByRole('button', { name: /restore/i });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);
    await waitFor(() => expect(onRestore).toHaveBeenCalledWith(expect.objectContaining({ id: 'k1' })));
  });
});
