// LOOM Composition (T5.4 M3) — a panel's placement-aware host (view).
//
// Wraps one studio panel's content. Docked → an in-flow div toggled with CSS `hidden`
// (the M2 behaviour, byte-identical when the windowing flag is OFF or there's no
// provider). Floated → the SAME children rendered inside a FloatingWindow (portaled
// to body). The children's React position stays under DockSlot either way, so the
// only thing a dock↔float flip reconciles is the chrome; live state (the co-writer
// SSE) survives because it's hoisted above this layer (LiveStateContext, M1).
import type { ReactNode } from 'react';
import type { Rect, WorkspacePanelId } from '../../workspace/types';
import { FloatingWindow } from './FloatingWindow';

export function DockSlot({
  id, active, floated, rect, title, zIndex, onMove, onResize, onDock, onFocus, children,
}: {
  id: WorkspacePanelId;
  active: boolean;       // the focused docked panel (drives the visible/hidden div)
  floated: boolean;      // placement === 'float' (only ever true when the flag is ON)
  rect: Rect;
  title: ReactNode;
  zIndex: number;
  onMove: (rect: Rect) => void;
  onResize: (rect: Rect) => void;
  onDock: () => void;
  onFocus?: () => void;
  children: ReactNode;
}) {
  if (floated) {
    return (
      <FloatingWindow
        title={title}
        rect={rect}
        zIndex={zIndex}
        onMove={onMove}
        onResize={onResize}
        onDock={onDock}
        onFocus={onFocus}
      >
        {children}
      </FloatingWindow>
    );
  }
  return (
    <div data-testid={`dock-slot-${id}`} className={active ? '' : 'hidden'}>
      {children}
    </div>
  );
}
