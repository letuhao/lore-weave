// Top-bar trigger for the panel-layout preset menu. Owns open/close + reads the live dock (panel
// count + width) at open time, then hands a picked preset to the host's applyDockLayout seam. The
// menu itself (LayoutPicker) is presentational; this component is the only place that touches the
// dock api, keeping the "one seam" discipline.
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { LayoutGrid } from 'lucide-react';
import { useStudioHost } from '../host/StudioHostProvider';
import { LayoutPicker } from '../layout/LayoutPicker';
import type { LayoutPreset } from '../layout/dockLayout';

export function StudioLayoutButton() {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const [open, setOpen] = useState(false);
  // Snapshotted at open time from the live dock — not reactive, but the menu is short-lived and a
  // fresh open re-reads. Zero when the dock api isn't ready yet (menu then guides "open panels").
  const [snapshot, setSnapshot] = useState({ panelCount: 0, dockWidth: 0 });

  const openMenu = useCallback(() => {
    const api = host._dockApiRef.current;
    setSnapshot({ panelCount: api?.panels.length ?? 0, dockWidth: api?.width ?? 0 });
    setOpen(true);
  }, [host]);

  // Escape closes (matches the palette/dialog dismissal convention).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const onPick = useCallback((preset: LayoutPreset) => {
    host.applyDockLayout(preset.cols, preset.rows);
    setOpen(false);
  }, [host]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openMenu())}
        data-testid="studio-layout-button"
        aria-haspopup="menu"
        aria-expanded={open}
        title={t('layout.title', { defaultValue: 'Panel layout' })}
        className={`flex h-7 w-7 items-center justify-center rounded-md ${
          open ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
      >
        <LayoutGrid className="h-4 w-4" />
      </button>

      {open && (
        <>
          {/* Outside-click backdrop (transparent, full-window) — dismiss on any click elsewhere. */}
          <div
            className="fixed inset-0 z-40"
            data-testid="studio-layout-backdrop"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-50 mt-1">
            <LayoutPicker panelCount={snapshot.panelCount} dockWidth={snapshot.dockWidth} onPick={onPick} />
          </div>
        </>
      )}
    </div>
  );
}
