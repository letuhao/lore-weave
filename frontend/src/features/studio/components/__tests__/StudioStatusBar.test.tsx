import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioStatusBar } from '../StudioStatusBar';

describe('StudioStatusBar', () => {
  it('shows the book language and the ⌘P hint', () => {
    render(<StudioStatusBar bookLanguage="vi" bottomOpen={false} onToggleBottom={vi.fn()} />);
    expect(screen.getByText('vi')).toBeTruthy();
    expect(screen.getByText('⌘P')).toBeTruthy();
  });

  it('toggles the bottom panel', () => {
    const onToggleBottom = vi.fn();
    render(<StudioStatusBar bottomOpen={false} onToggleBottom={onToggleBottom} />);
    fireEvent.click(screen.getByTestId('studio-toggle-bottom'));
    expect(onToggleBottom).toHaveBeenCalledTimes(1);
  });

  it('reflects the open state on the toggle (active styling)', () => {
    render(<StudioStatusBar bottomOpen onToggleBottom={vi.fn()} />);
    expect(screen.getByTestId('studio-toggle-bottom').className).toContain('text-primary');
  });
});
