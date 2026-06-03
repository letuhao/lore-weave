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

  it('intent/context/files are disabled (slices 2–4)', () => {
    render(<ModeSelector mode="draft" onSelect={vi.fn()} onUseGaps={vi.fn()} />);
    for (const m of ['intent', 'context', 'files']) {
      expect(screen.getByTestId(`compose-mode-${m}`)).toBeDisabled();
    }
  });
});
