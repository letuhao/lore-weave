import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';
import { StudioLayoutButton } from '../StudioLayoutButton';

/** A fake DockviewApi with `n` panels, recording addGroup so we can prove a reflow ran. */
function fakeApi(n: number, width = 4000) {
  let seq = 0;
  const mk = () => ({ id: `g${seq++}` });
  const anchor = mk();
  const addGroup = vi.fn(() => mk());
  const panels = Array.from({ length: n }, () => {
    const p = { group: anchor, api: { moveTo: vi.fn((o: { group: { id: string } }) => { p.group = o.group; }), setActive: vi.fn() } };
    return p;
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return { get panels() { return panels; }, activePanel: panels[0], width, addGroup } as any;
}

let captured: StudioHost | null = null;
function Capture() { captured = useStudioHost(); return null; }

function setup(dockPanels: number) {
  captured = null;
  render(
    <StudioHostProvider bookId="b1">
      <Capture />
      <StudioLayoutButton />
    </StudioHostProvider>,
  );
  act(() => { captured!._dockApiRef.current = fakeApi(dockPanels); });
}

describe('StudioLayoutButton', () => {
  it('toggles the layout menu open and closed', () => {
    setup(4);
    expect(screen.queryByTestId('studio-layout-picker')).toBeNull();
    fireEvent.click(screen.getByTestId('studio-layout-button'));
    expect(screen.getByTestId('studio-layout-picker')).toBeTruthy();
    fireEvent.click(screen.getByTestId('studio-layout-button'));
    expect(screen.queryByTestId('studio-layout-picker')).toBeNull();
  });

  it('picking a preset applies the reflow to the live dock, then closes', () => {
    setup(4);
    const api = captured!._dockApiRef.current!;
    fireEvent.click(screen.getByTestId('studio-layout-button'));
    fireEvent.click(screen.getByTestId('studio-layout-preset-cols4'));
    // 4 panels → 4 columns = 3 new groups created on the real api (proves the whole seam ran).
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((api as any).addGroup).toHaveBeenCalledTimes(3);
    expect(screen.queryByTestId('studio-layout-picker')).toBeNull(); // closed after pick
  });

  it('Escape and the backdrop both dismiss the menu', () => {
    setup(4);
    fireEvent.click(screen.getByTestId('studio-layout-button'));
    fireEvent.click(screen.getByTestId('studio-layout-backdrop'));
    expect(screen.queryByTestId('studio-layout-picker')).toBeNull();

    fireEvent.click(screen.getByTestId('studio-layout-button'));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('studio-layout-picker')).toBeNull();
  });

  it('reflects the live panel count: <2 panels disables multi-cell presets', () => {
    setup(1);
    fireEvent.click(screen.getByTestId('studio-layout-button'));
    expect((screen.getByTestId('studio-layout-preset-cols2') as HTMLButtonElement).disabled).toBe(true);
  });
});
