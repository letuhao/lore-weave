import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { StudioStatusBar } from '../StudioStatusBar';
import { StudioHostProvider, useRegisterStatusBarItem } from '../../host/StudioHostProvider';

// The status bar reads contributed items from the host (#11 F2) — always render inside a provider.
const withHost = (ui: ReactNode) => render(<StudioHostProvider bookId="b1">{ui}</StudioHostProvider>);

describe('StudioStatusBar', () => {
  it('shows the book language and the ⌘P hint', () => {
    withHost(<StudioStatusBar bookLanguage="vi" bottomOpen={false} onToggleBottom={vi.fn()} />);
    expect(screen.getByText('vi')).toBeTruthy();
    expect(screen.getByText('⌘P')).toBeTruthy();
  });

  it('toggles the bottom panel', () => {
    const onToggleBottom = vi.fn();
    withHost(<StudioStatusBar bottomOpen={false} onToggleBottom={onToggleBottom} />);
    fireEvent.click(screen.getByTestId('studio-toggle-bottom'));
    expect(onToggleBottom).toHaveBeenCalledTimes(1);
  });

  it('reflects the open state on the toggle (active styling)', () => {
    withHost(<StudioStatusBar bottomOpen onToggleBottom={vi.fn()} />);
    expect(screen.getByTestId('studio-toggle-bottom').className).toContain('text-primary');
  });

  it('renders contributed items (register → visible, unmount → gone)', () => {
    function Contributor() {
      useRegisterStatusBarItem({
        id: 'demo', side: 'right', component: () => <span data-testid="sbi-demo">42</span>,
      });
      return null;
    }
    const { rerender } = render(
      <StudioHostProvider bookId="b1">
        <Contributor />
        <StudioStatusBar bottomOpen={false} onToggleBottom={vi.fn()} />
      </StudioHostProvider>,
    );
    expect(screen.getByTestId('sbi-demo').textContent).toBe('42');
    rerender(
      <StudioHostProvider bookId="b1">
        <StudioStatusBar bottomOpen={false} onToggleBottom={vi.fn()} />
      </StudioHostProvider>,
    );
    expect(screen.queryByTestId('sbi-demo')).toBeNull();
  });
});
