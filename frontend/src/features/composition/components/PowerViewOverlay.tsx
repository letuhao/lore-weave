// LOOM Composition (T5.5) — Story Map Power-view.
// A full-screen overlay hosting the five story-map views behind a switcher.
// Mount-on-open (the parent conditionally renders it); within the overlay,
// switching views is CSS show/hide — NOT a remount — so each view keeps its
// pan/zoom/selection. Esc or "Back to editor" exits. Independent instances from
// the side-panel subtabs (CLARIFY T5.5).
import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useModalFocusTrap } from '../hooks/useModalFocusTrap';
import type { Work } from '../types';
import { SceneGraphCanvas } from './SceneGraphCanvas';
import { TimelineView } from './TimelineView';
import { BeatSheetView } from './BeatSheetView';
import { RelationshipMap } from './RelationshipMap';
import { WorldMap } from './WorldMap';

type PowerView = 'graph' | 'timeline' | 'beats' | 'relmap' | 'worldmap';
const VIEWS: PowerView[] = ['graph', 'timeline', 'beats', 'relmap', 'worldmap'];

type Props = {
  work: Work;
  bookId: string;
  chapterId: string;
  token: string | null;
  onClose: () => void;
  /** open the Cast tab focused on a character (from WorldMap); exits the overlay first */
  onViewCast?: (name: string) => void;
  /** WS-B3 M3 — a what-if promoted to a derivative; switch the studio + exit the overlay. */
  onPromoted?: (derivative: Work) => void;
};

export function PowerViewOverlay({ work, bookId, chapterId, token, onClose, onViewCast, onPromoted }: Props) {
  const { t } = useTranslation('composition');
  const [view, setView] = useState<PowerView>('graph');
  const dialogRef = useRef<HTMLDivElement>(null);

  // a11y (WS-E): trap Tab within the modal + move focus to the switcher on open +
  // restore to the trigger on close; Escape exits (stopPropagation so a sibling
  // window-level Esc consumer can't also fire). Replaces the prior window-level
  // Esc-only listener — the trap is bound on the dialog element.
  useModalFocusTrap(dialogRef, onClose);

  // Portal to <body> so `fixed inset-0` is viewport-relative even though the
  // overlay is mounted deep inside the resizable-panel tree (a transformed
  // ancestor would otherwise clip it — the panels already use translate-x).
  return createPortal(
    <div
      ref={dialogRef}
      data-testid="power-view-overlay"
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      className="fixed inset-0 z-50 flex flex-col bg-white dark:bg-neutral-950 outline-none"
    >
      <div className="flex flex-shrink-0 items-center gap-1 border-b px-2 py-1.5">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            data-testid={`power-view-tab-${v}`}
            className={`rounded px-2.5 py-1 text-sm ${view === v ? 'bg-neutral-100 font-medium dark:bg-neutral-800' : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'}`}
            onClick={() => setView(v)}
            aria-pressed={view === v}
          >
            {t(v, { defaultValue: v })}
          </button>
        ))}
        <button
          type="button"
          data-testid="power-view-close"
          className="ml-auto rounded border px-2.5 py-1 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
          onClick={onClose}
        >
          {t('view.back_to_editor', { defaultValue: 'Back to editor' })}
          <span className="ml-1.5 text-xs text-neutral-400">Esc</span>
        </button>
      </div>

      {/* All views stay MOUNTED; only the active one is shown (no remount on switch). */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className={view === 'graph' ? 'h-full' : 'hidden'}>
          <SceneGraphCanvas work={work} bookId={bookId} token={token} onPromoted={onPromoted} />
        </div>
        <div className={view === 'timeline' ? 'h-full' : 'hidden'}>
          <TimelineView bookId={bookId} chapterId={chapterId} token={token} />
        </div>
        <div className={view === 'beats' ? 'h-full' : 'hidden'}>
          <BeatSheetView bookId={bookId} projectId={work.project_id} token={token} />
        </div>
        <div className={view === 'relmap' ? 'h-full' : 'hidden'}>
          <RelationshipMap bookId={bookId} token={token} />
        </div>
        <div className={view === 'worldmap' ? 'h-full' : 'hidden'}>
          <WorldMap
            work={work}
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            onViewCast={(name) => { onClose(); onViewCast?.(name); }}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
