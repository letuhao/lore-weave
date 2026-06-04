import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModeSelector } from '../ModeSelector';

describe('ModeSelector', () => {
  it('selecting draft calls onSelect; draft is the active path', () => {
    const onSelect = vi.fn();
    const onUseGaps = vi.fn();
    render(<ModeSelector mode="draft" onSelect={onSelect} onUseGaps={onUseGaps} />);
    fireEvent.click(screen.getByTestId('compose-mode-draft'));
    expect(onSelect).toHaveBeenCalledWith('draft');
    expect(onUseGaps).not.toHaveBeenCalled();
  });

  it('clicking the gap mode routes to the Gaps tab (onUseGaps), not onSelect', () => {
    const onSelect = vi.fn();
    const onUseGaps = vi.fn();
    render(<ModeSelector mode="draft" onSelect={onSelect} onUseGaps={onUseGaps} />);
    fireEvent.click(screen.getByTestId('compose-mode-gap'));
    expect(onUseGaps).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it.each(['context', 'files'])('selecting %s calls onSelect (active mode)', (m) => {
    const onSelect = vi.fn();
    render(<ModeSelector mode="draft" onSelect={onSelect} onUseGaps={vi.fn()} />);
    fireEvent.click(screen.getByTestId(`compose-mode-${m}`));
    expect(onSelect).toHaveBeenCalledWith(m);
  });

  it('intent is disabled (slice 4)', () => {
    render(<ModeSelector mode="draft" onSelect={vi.fn()} onUseGaps={vi.fn()} />);
    expect(screen.getByTestId('compose-mode-intent')).toBeDisabled();
  });
});
