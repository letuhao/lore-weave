import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DockSlot } from '../DockSlot';
import type { Rect } from '../../../workspace/types';

const RECT: Rect = { x: 10, y: 10, w: 400, h: 300 };

function setup(over: Partial<Parameters<typeof DockSlot>[0]> = {}) {
  const props = {
    id: 'compose' as const,
    active: false,
    floated: false,
    rect: RECT,
    title: 'Compose',
    zIndex: 40,
    onMove: vi.fn(),
    onResize: vi.fn(),
    onDock: vi.fn(),
    onFocus: vi.fn(),
    ...over,
  };
  render(<DockSlot {...props}><div data-testid="body">body</div></DockSlot>);
  return props;
}

describe('DockSlot (T5.4 M3)', () => {
  it('docked + inactive → hidden in-flow div (M2 behaviour preserved)', () => {
    setup({ floated: false, active: false });
    const slot = screen.getByTestId('dock-slot-compose');
    expect(slot).toHaveClass('hidden');
    expect(screen.queryByTestId('floating-window')).toBeNull();
    expect(screen.getByTestId('body')).toBeInTheDocument();   // still MOUNTED
  });

  it('docked + active → visible in-flow div (no hidden class)', () => {
    setup({ floated: false, active: true });
    expect(screen.getByTestId('dock-slot-compose')).not.toHaveClass('hidden');
  });

  it('floated → renders the SAME children inside a FloatingWindow, not the in-flow div', () => {
    setup({ floated: true });
    expect(screen.queryByTestId('dock-slot-compose')).toBeNull();   // no in-flow div
    expect(screen.getByTestId('floating-window')).toBeInTheDocument();
    expect(screen.getByTestId('body')).toBeInTheDocument();         // children re-parented, still there
  });

  it('floated window docks back via the dock button', () => {
    const p = setup({ floated: true });
    fireEvent.click(screen.getByTestId('floating-window-dock'));
    expect(p.onDock).toHaveBeenCalledTimes(1);
  });

  it('mounted=false renders nothing (a popped-out / non-solo panel lives elsewhere) (M4)', () => {
    setup({ mounted: false, active: true });
    expect(screen.queryByTestId('dock-slot-compose')).toBeNull();
    expect(screen.queryByTestId('floating-window')).toBeNull();
    expect(screen.queryByTestId('body')).toBeNull();   // children not rendered here at all
  });
});
