import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';

describe('StatusBadge', () => {
  it('renders default label for variant', () => {
    render(<StatusBadge variant="private" />);
    expect(screen.getByText('Private')).toBeInTheDocument();
  });

  it('renders custom label when provided', () => {
    render(<StatusBadge variant="public" label="Open" />);
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.queryByText('Public')).not.toBeInTheDocument();
  });

  it('renders all visibility variants', () => {
    const { unmount: u1 } = render(<StatusBadge variant="private" />);
    expect(screen.getByText('Private')).toBeInTheDocument();
    u1();

    const { unmount: u2 } = render(<StatusBadge variant="unlisted" />);
    expect(screen.getByText('Unlisted')).toBeInTheDocument();
    u2();

    render(<StatusBadge variant="public" />);
    expect(screen.getByText('Public')).toBeInTheDocument();
  });

  it('renders all status variants', () => {
    const variants = [
      { v: 'running' as const, l: 'Running' },
      { v: 'pending' as const, l: 'Pending' },
      { v: 'completed' as const, l: 'Completed' },
      { v: 'failed' as const, l: 'Failed' },
    ];
    for (const { v, l } of variants) {
      const { unmount } = render(<StatusBadge variant={v} />);
      expect(screen.getByText(l)).toBeInTheDocument();
      unmount();
    }
  });

  it('applies additional className', () => {
    const { container } = render(<StatusBadge variant="active" className="my-extra" />);
    expect(container.firstChild).toHaveClass('my-extra');
  });
});
