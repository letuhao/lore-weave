import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

import { WikiGenBadge } from '../WikiGenBadge';

describe('WikiGenBadge', () => {
  it('renders nothing for a human-authored article (null status)', () => {
    const { container } = render(<WikiGenBadge status={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('hides the clean "generated" marker in subtle (sidebar) mode', () => {
    const { container } = render(<WikiGenBadge status="generated" subtle />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the clean AI marker in full mode', () => {
    render(<WikiGenBadge status="generated" />);
    expect(screen.getByTestId('wiki-gen-badge-generated')).toBeTruthy();
  });

  it('always shows needs_review and blocked, even subtle', () => {
    const { rerender } = render(<WikiGenBadge status="needs_review" subtle />);
    expect(screen.getByTestId('wiki-gen-badge-needs_review')).toBeTruthy();
    rerender(<WikiGenBadge status="blocked" subtle />);
    expect(screen.getByTestId('wiki-gen-badge-blocked')).toBeTruthy();
  });
});
