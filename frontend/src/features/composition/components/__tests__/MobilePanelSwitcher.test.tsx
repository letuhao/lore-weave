import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MobilePanelSwitcher } from '../MobilePanelSwitcher';

const label = (id: string) => `label:${id}`;

describe('MobilePanelSwitcher (M5a)', () => {
  it('shows the active panel name in the trigger; the sheet is closed initially', () => {
    render(<MobilePanelSwitcher ids={['compose', 'graph']} active="compose" onSelect={vi.fn()} label={label} />);
    expect(screen.getByTestId('mobile-panel-switcher').textContent).toContain('label:compose');
    expect(screen.queryByTestId('mobile-panel-sheet')).toBeNull();
  });

  it('opens the bottom sheet and selecting a panel calls onSelect + closes', () => {
    const onSelect = vi.fn();
    render(<MobilePanelSwitcher ids={['compose', 'graph', 'cast']} active="compose" onSelect={onSelect} label={label} />);
    fireEvent.click(screen.getByTestId('mobile-panel-switcher'));
    expect(screen.getByTestId('mobile-panel-sheet')).toBeTruthy();
    fireEvent.click(screen.getByTestId('mobile-panel-graph'));
    expect(onSelect).toHaveBeenCalledWith('graph');
    expect(screen.queryByTestId('mobile-panel-sheet')).toBeNull(); // closed after pick
  });

  it('marks the active panel with aria-current in the list', () => {
    render(<MobilePanelSwitcher ids={['compose', 'graph']} active="graph" onSelect={vi.fn()} label={label} />);
    fireEvent.click(screen.getByTestId('mobile-panel-switcher'));
    expect(screen.getByTestId('mobile-panel-graph').getAttribute('aria-current')).toBe('true');
    expect(screen.getByTestId('mobile-panel-compose').getAttribute('aria-current')).toBe('false');
  });

  it('Escape closes the sheet', () => {
    render(<MobilePanelSwitcher ids={['compose']} active="compose" onSelect={vi.fn()} label={label} />);
    fireEvent.click(screen.getByTestId('mobile-panel-switcher'));
    expect(screen.getByTestId('mobile-panel-sheet')).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('mobile-panel-sheet')).toBeNull();
  });
});
