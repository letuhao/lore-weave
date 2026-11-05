import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EffortSelect } from '../EffortSelect';

describe('EffortSelect (unified 5-level)', () => {
  it('opens the menu, lists all 5 levels, emits the picked level', () => {
    const onChange = vi.fn();
    render(<EffortSelect value="off" onChange={onChange} />);

    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
    fireEvent.click(screen.getByTestId('effort-select'));
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();
    for (const l of ['off', 'low', 'medium', 'high', 'auto']) {
      expect(screen.getByTestId(`effort-select-opt-${l}`)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByTestId('effort-select-opt-high'));
    expect(onChange).toHaveBeenCalledWith('high');
    expect(screen.queryByTestId('effort-select-menu')).toBeNull(); // closes after pick
  });

  it('renders the auto level and respects disabled', () => {
    render(<EffortSelect value="auto" onChange={vi.fn()} disabled />);
    expect(screen.getByTestId('effort-select')).toBeDisabled();
  });

  // #262 — the open menu must be a body-level PORTAL, not an inline absolute child of
  // the control row. In the compose view the control row sits below the what-if
  // promote bar; the old inline `absolute bottom-full z-20` menu stayed inside the
  // row's stacking context and the bar's subtree won the browser hit test, so the
  // menu rendered but every option click landed on the bar behind it. Escaping the
  // trigger's subtree entirely is the property that kills that interception class.
  it('renders the open menu OUTSIDE the trigger subtree as a fixed body-level portal (#262)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <div data-testid="compose-row"><EffortSelect value="off" onChange={onChange} /></div>,
    );
    fireEvent.click(screen.getByTestId('effort-select'));
    const menu = screen.getByTestId('effort-select-menu');
    expect(container.querySelector('[data-testid="effort-select-menu"]')).toBeNull();
    expect(container.ownerDocument.body.contains(menu)).toBe(true);
    expect(getComputedStyle(menu).position).toBe('fixed');
    // Options are still clickable in the portal (the pick path is unchanged).
    fireEvent.click(screen.getByTestId('effort-select-opt-low'));
    expect(onChange).toHaveBeenCalledWith('low');
  });

  it('a mousedown inside the portal menu keeps it open; outside closes it (#262)', () => {
    render(<EffortSelect value="off" onChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId('effort-select'));
    // The portal menu is outside the trigger subtree — the outside-click handler must
    // count it as "inside" or the menu would close before the option's click lands.
    fireEvent.mouseDown(screen.getByTestId('effort-select-opt-medium'));
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
  });
});
