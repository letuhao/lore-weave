import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DockRail } from '../DockRail';
import type { WorkspacePanelId } from '../../../workspace/types';

function setup(over: Partial<Parameters<typeof DockRail>[0]> = {}) {
  const props = {
    visibleIds: ['compose', 'cast', 'grounding'] as WorkspacePanelId[],
    hiddenIds: ['flywheel'] as WorkspacePanelId[],
    active: 'compose' as WorkspacePanelId,
    onSelect: vi.fn(),
    onReorder: vi.fn(),
    onHide: vi.fn(),
    onShow: vi.fn(),
    onFloat: vi.fn(),
    onPopout: vi.fn(),
    ...over,
  };
  render(<DockRail {...props} rightSlot={<button data-testid="rs">RS</button>} />);
  return props;
}

describe('DockRail (T5.4 M2)', () => {
  it('renders the visible docked tabs + the right slot', () => {
    setup();
    expect(screen.getByTestId('dock-tab-compose')).toBeInTheDocument();
    expect(screen.getByTestId('dock-tab-cast')).toBeInTheDocument();
    expect(screen.getByTestId('dock-tab-grounding')).toBeInTheDocument();
    expect(screen.getByTestId('rs')).toBeInTheDocument();
  });

  it('clicking a tab selects it', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('dock-select-cast'));
    expect(p.onSelect).toHaveBeenCalledWith('cast');
  });

  it('the × hides a panel', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('dock-hide-grounding'));
    expect(p.onHide).toHaveBeenCalledWith('grounding');
  });

  it('the ⤢ floats a panel (M3)', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('dock-float-cast'));
    expect(p.onFloat).toHaveBeenCalledWith('cast');
  });

  it('the ⮬ pops a panel out to an OS window (M4)', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('dock-popout-cast'));
    expect(p.onPopout).toHaveBeenCalledWith('cast');
  });

  it('the component picker re-shows a hidden panel', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('dock-component-picker')); // open the menu
    fireEvent.click(screen.getByTestId('dock-show-flywheel'));
    expect(p.onShow).toHaveBeenCalledWith('flywheel');
  });

  it('the picker is absent when nothing is hidden', () => {
    setup({ hiddenIds: [] });
    expect(screen.queryByTestId('dock-component-picker')).toBeNull();
  });
});
