// LOOM Composition (T5.4 M3) — an in-app floating window (view).
//
// A draggable + resizable window, PORTALED to <body> so its `position: fixed`
// geometry is viewport-relative even under a transformed ancestor (a translate-x
// studio panel would otherwise clip it). The child panel is re-parented here when
// its placement flips to 'float'; live state survives because the SSE streams are
// hoisted ABOVE this layer (LiveStateContext, M1) — a placement change reconciles
// the view but never the stream.
//
// Drag/resize is dependency-free: a pointerdown on the header (move) or the SE
// corner (resize) starts a gesture; window-level pointermove/up listeners (attached
// only WHILE dragging — synchronization, the legit useEffect use) translate the
// captured origin rect. onMove/onResize report the new rect; the owner persists it.
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import type { Rect } from '../../workspace/types';

const MIN_W = 280;
const MIN_H = 180;
const EDGE_MARGIN = 48;   // keep at least this much of the window on-screen (header reachable)

type Gesture = { kind: 'move' | 'resize'; startX: number; startY: number; orig: Rect };

// The candidate rect from a gesture's pointer delta (visual-follow; unclamped on the
// top/left for resize floors only — the viewport clamp is applied once, at commit).
function applyDelta(g: Gesture, dx: number, dy: number): Rect {
  if (g.kind === 'move') return { ...g.orig, x: g.orig.x + dx, y: g.orig.y + dy };
  return { ...g.orig, w: Math.max(MIN_W, g.orig.w + dx), h: Math.max(MIN_H, g.orig.h + dy) };
}

// Clamp the committed rect so a window can't be dragged/sized off-screen with no way
// back (its rail tab is gone once floated). Move keeps a header-grip in the viewport;
// resize re-asserts the min floor.
function clampRect(r: Rect, kind: Gesture['kind']): Rect {
  if (kind === 'resize') return { ...r, w: Math.max(MIN_W, r.w), h: Math.max(MIN_H, r.h) };
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1024;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 768;
  return {
    ...r,
    x: Math.min(Math.max(0, r.x), Math.max(0, vw - EDGE_MARGIN)),
    y: Math.min(Math.max(0, r.y), Math.max(0, vh - EDGE_MARGIN)),
  };
}

export function FloatingWindow({
  title, rect, zIndex, onMove, onResize, onDock, onFocus, children,
}: {
  title: ReactNode;
  rect: Rect;
  zIndex: number;
  onMove: (rect: Rect) => void;
  onResize: (rect: Rect) => void;
  onDock: () => void;
  onFocus?: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation('composition');
  const [gesture, setGesture] = useState<Gesture | null>(null);
  // The visual rect DURING a gesture — local so dragging follows the cursor WITHOUT
  // dispatching (no CompositionPanel re-render of all 20 panels, no localStorage write)
  // on every pointermove. The committed rect is reported ONCE on release (/review-impl
  // MED): the owner persists it then, not 60×/sec.
  const [live, setLive] = useState<Rect | null>(null);
  // Keep the latest callbacks in a ref so the drag effect doesn't re-subscribe (and
  // drop an in-flight gesture) when the parent re-renders with new closures.
  const cb = useRef({ onMove, onResize });
  cb.current = { onMove, onResize };

  useEffect(() => {
    if (!gesture) return;
    const candidate = (e: PointerEvent) => applyDelta(gesture, e.clientX - gesture.startX, e.clientY - gesture.startY);
    const onPointerMove = (e: PointerEvent) => setLive(candidate(e));   // visual only
    const end = (e: PointerEvent) => {
      const finalRect = clampRect(candidate(e), gesture.kind);          // clamp + commit once
      if (gesture.kind === 'move') cb.current.onMove(finalRect);
      else cb.current.onResize(finalRect);
      setGesture(null);
      setLive(null);
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
  }, [gesture]);

  const start = (kind: Gesture['kind']) => (e: React.PointerEvent) => {
    e.preventDefault();
    onFocus?.();
    setGesture({ kind, startX: e.clientX, startY: e.clientY, orig: rect });
  };

  const shown = live ?? rect;   // follow the gesture visually; fall back to the persisted rect

  return createPortal(
    <div
      role="dialog"
      aria-label={typeof title === 'string' ? title : undefined}
      data-testid="floating-window"
      onPointerDown={onFocus}
      className="fixed flex flex-col overflow-hidden rounded-lg border border-neutral-300 bg-white shadow-2xl dark:border-neutral-700 dark:bg-neutral-900"
      style={{ left: shown.x, top: shown.y, width: shown.w, height: shown.h, zIndex }}
    >
      <div
        data-testid="floating-window-header"
        onPointerDown={start('move')}
        className="flex shrink-0 cursor-move select-none items-center gap-2 border-b border-neutral-200 bg-neutral-50 px-2 py-1 text-xs font-medium dark:border-neutral-700 dark:bg-neutral-800"
      >
        <span className="min-w-0 flex-1 truncate">{title}</span>
        <button
          type="button"
          data-testid="floating-window-dock"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onDock}
          className="shrink-0 rounded px-1.5 py-0.5 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-700 dark:hover:bg-neutral-700"
          aria-label={t('dock.dock', { defaultValue: 'Dock' })}
          title={t('dock.dock', { defaultValue: 'Dock' })}
        >⤓</button>
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto [overflow-wrap:anywhere]">{children}</div>
      <div
        data-testid="floating-window-resize"
        onPointerDown={start('resize')}
        className="absolute bottom-0 right-0 h-3.5 w-3.5 cursor-se-resize"
        aria-hidden="true"
        style={{ touchAction: 'none' }}
      >
        <div className="absolute bottom-0.5 right-0.5 h-2 w-2 border-b-2 border-r-2 border-neutral-400" />
      </div>
    </div>,
    document.body,
  );
}
