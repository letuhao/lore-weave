import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CopyButton } from '../CopyButton';

describe('CopyButton', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders default "Copy" label', () => {
    render(<CopyButton value="test" />);
    expect(screen.getByText('Copy')).toBeInTheDocument();
  });

  it('renders custom label', () => {
    render(<CopyButton value="test" label="Copy link" />);
    expect(screen.getByText('Copy link')).toBeInTheDocument();
  });

  it('copies value to clipboard on click', async () => {
    render(<CopyButton value="hello world" />);
    await userEvent.click(screen.getByRole('button'));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('hello world');
  });

  it('shows "Copied!" after click', async () => {
    render(<CopyButton value="test" />);
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByText('Copied!')).toBeInTheDocument();
  });
});
