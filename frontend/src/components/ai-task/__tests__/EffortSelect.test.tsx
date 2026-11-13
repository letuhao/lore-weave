import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as Dialog from '@radix-ui/react-dialog';
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

  // P1 (#320) — the portal menu is a direct child of document.body. A modal Radix
  // dialog sets body pointer-events to none and re-enables them only on its own
  // layers (@radix-ui/react-dismissable-layer: body.style.pointerEvents = 'none'),
  // so a menu without its own pointer-events override renders above the dialog yet
  // takes no clicks in a real browser. jsdom does no hit-testing, so the guard is
  // the computed style that governs hit-testing in the browser.
  it('menu restores pointer events when a modal disables them on body (P1 #320)', () => {
    document.body.style.pointerEvents = 'none';
    try {
      render(<EffortSelect value="off" onChange={vi.fn()} />);
      fireEvent.click(screen.getByTestId('effort-select'));
      expect(getComputedStyle(screen.getByTestId('effort-select-menu')).pointerEvents).toBe('auto');
    } finally {
      document.body.style.pointerEvents = '';
    }
  });

  it('menu stays usable inside a real Radix modal dialog (P1 #320)', () => {
    const onChange = vi.fn();
    render(
      <Dialog.Root open>
        <Dialog.Portal>
          <Dialog.Overlay />
          <Dialog.Content>
            <Dialog.Title>Pick effort</Dialog.Title>
            <EffortSelect value="off" onChange={onChange} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>,
    );
    // The dialog is genuinely modal: Radix disabled pointer events on body.
    expect(document.body.style.pointerEvents).toBe('none');
    fireEvent.click(screen.getByTestId('effort-select'));
    const menu = screen.getByTestId('effort-select-menu');
    expect(getComputedStyle(menu).pointerEvents).toBe('auto');
    fireEvent.click(screen.getByTestId('effort-select-opt-high'));
    expect(onChange).toHaveBeenCalledWith('high');
  });

  // P2 (#320) — the portal lives at the end of body, so after opening with the
  // keyboard the next Tab no longer reaches the menu: in the compose view it
  // reaches the Diverge checkbox after the trigger. Focus must move into the menu
  // on open, travel between options with arrows, and return to the trigger on
  // Escape — without dismissing an enclosing dialog.
  it('focus moves into the menu on open, arrows travel, Escape closes and restores focus (P2 #320)', async () => {
    const user = userEvent.setup();
    render(<EffortSelect value="medium" onChange={vi.fn()} />);
    const trigger = screen.getByTestId('effort-select');
    await user.click(trigger);
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByTestId('effort-select-opt-medium'));
    await user.keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(screen.getByTestId('effort-select-opt-high'));
    await user.keyboard('{ArrowUp}');
    expect(document.activeElement).toBe(screen.getByTestId('effort-select-opt-medium'));
    await user.keyboard('{End}');
    expect(document.activeElement).toBe(screen.getByTestId('effort-select-opt-auto'));
    await user.keyboard('{Home}');
    expect(document.activeElement).toBe(screen.getByTestId('effort-select-opt-off'));
    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('Escape closes the menu but not the enclosing dialog (P2 #320)', async () => {
    const user = userEvent.setup();
    render(
      <Dialog.Root open>
        <Dialog.Portal>
          <Dialog.Overlay />
          <Dialog.Content>
            <Dialog.Title>Pick effort</Dialog.Title>
            <EffortSelect value="off" onChange={vi.fn()} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>,
    );
    await user.click(screen.getByTestId('effort-select'));
    expect(screen.getByTestId('effort-select-menu')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('effort-select-menu')).toBeNull();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByTestId('effort-select'));
  });
});
