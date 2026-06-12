import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';

describe('StatusBadge', () => {
  // The global react-i18next mock returns the key, so default labels render as
  // `badge.<variant>` (the live `common.badge.*` strings are exercised in the
  // browser, not here). The custom-label path bypasses i18n entirely.
  it('renders default label key for variant', () => {
    render(<StatusBadge variant="private" />);
    expect(screen.getByText('badge.private')).toBeInTheDocument();
  });

  it('renders custom label when provided', () => {
    render(<StatusBadge variant="public" label="Open" />);
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.queryByText('badge.public')).not.toBeInTheDocument();
  });

  it('renders all visibility variants', () => {
    const { unmount: u1 } = render(<StatusBadge variant="private" />);
    expect(screen.getByText('badge.private')).toBeInTheDocument();
    u1();

    const { unmount: u2 } = render(<StatusBadge variant="unlisted" />);
    expect(screen.getByText('badge.unlisted')).toBeInTheDocument();
    u2();

    render(<StatusBadge variant="public" />);
    expect(screen.getByText('badge.public')).toBeInTheDocument();
  });

  it('renders all status variants', () => {
    const variants = ['running', 'pending', 'completed', 'failed'] as const;
    for (const v of variants) {
      const { unmount } = render(<StatusBadge variant={v} />);
      expect(screen.getByText(`badge.${v}`)).toBeInTheDocument();
      unmount();
    }
  });

  it('applies additional className', () => {
    const { container } = render(<StatusBadge variant="active" className="my-extra" />);
    expect(container.firstChild).toHaveClass('my-extra');
  });
});
