import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioBottomPanel } from '../StudioBottomPanel';

describe('StudioBottomPanel', () => {
  it('defaults to the Jobs tab and switches tabs', () => {
    render(<StudioBottomPanel onClose={vi.fn()} />);
    const panel = screen.getByTestId('studio-bottom');
    expect(panel.textContent).toContain('bottomStub.jobs');
    fireEvent.click(screen.getByText('bottom.generation'));
    expect(panel.textContent).toContain('bottomStub.generation');
    expect(panel.textContent).not.toContain('bottomStub.jobs');
  });

  it('fires onClose from the collapse control', () => {
    const onClose = vi.fn();
    render(<StudioBottomPanel onClose={onClose} />);
    fireEvent.click(screen.getByTitle('bottom.collapse'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
