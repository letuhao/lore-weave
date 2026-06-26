// LOOM Composition (T5.4 M2) — the "+" component picker: re-show a hidden dock
// panel. A small toggle-able menu listing the currently-hidden panels; selecting
// one re-docks it (onShow). Hidden when nothing is hideable (all panels visible).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { WorkspacePanelId } from '../../workspace/types';

export function ComponentPicker({ hiddenIds, onShow }: {
  hiddenIds: WorkspacePanelId[];
  onShow: (id: WorkspacePanelId) => void;
}) {
  const { t } = useTranslation('composition');
  const [open, setOpen] = useState(false);
  if (!hiddenIds.length) return null;

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        data-testid="dock-component-picker"
        className="rounded px-2 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={t('dock.addPanel', { defaultValue: 'Add panel' })}
      >＋</button>
      {open && (
        <ul
          data-testid="dock-picker-menu"
          className="absolute right-0 top-full z-30 mt-1 max-h-64 w-44 overflow-auto rounded border border-neutral-200 bg-white py-1 text-xs shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
        >
          {hiddenIds.map((id) => (
            <li key={id}>
              <button
                type="button"
                data-testid={`dock-show-${id}`}
                className="block w-full px-3 py-1 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800"
                onClick={() => { onShow(id); setOpen(false); }}
              >
                {t(id, { defaultValue: id })}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
