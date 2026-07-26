import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDialog } from '../ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    title: 'Delete book?',
    description: 'This action cannot be undone.',
    onConfirm: vi.fn(),
  };

  it('renders title and description when open', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('Delete book?')).toBeInTheDocument();
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(<ConfirmDialog {...defaultProps} open={false} />);
    expect(screen.queryByText('Delete book?')).not.toBeInTheDocument();
  });

  it('shows default button labels', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('Cancel')).toBeInTheDocument();
    expect(screen.getByText('Confirm')).toBeInTheDocument();
  });

  it('shows custom button labels', () => {
    render(<ConfirmDialog {...defaultProps} confirmLabel="Delete" cancelLabel="Keep" />);
    expect(screen.getByText('Delete')).toBeInTheDocument();
    expect(screen.getByText('Keep')).toBeInTheDocument();
  });

  it('calls onConfirm when confirm button is clicked', async () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog {...defaultProps} onConfirm={onConfirm} />);
    await userEvent.click(screen.getByText('Confirm'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('disables confirm button when loading', () => {
    render(<ConfirmDialog {...defaultProps} loading />);
    expect(screen.getByText('Confirm')).toBeDisabled();
  });

  // bug #14 — AWS-style typed confirmation
  it('gates confirm behind a typed phrase and enables only on exact match', async () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog {...defaultProps} confirmLabel="Rebuild" confirmationPhrase="My Project" onConfirm={onConfirm} />);
    const confirmBtn = screen.getByText('Rebuild');
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByTestId('confirm-phrase-input');
    await userEvent.type(input, 'My Proj');
    expect(confirmBtn).toBeDisabled(); // partial — still gated
    await userEvent.type(input, 'ect');
    expect(confirmBtn).toBeEnabled();
    await userEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('blocks paste into the typed-confirmation input (no copy-paste)', async () => {
    render(<ConfirmDialog {...defaultProps} confirmationPhrase="DELETE" />);
    const input = screen.getByTestId('confirm-phrase-input') as HTMLInputElement;
    input.focus();
    await userEvent.paste('DELETE');
    expect(input.value).toBe(''); // paste prevented → still gated
    expect(screen.getByText('Confirm')).toBeDisabled();
  });
});
