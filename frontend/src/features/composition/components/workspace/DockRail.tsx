// LOOM Composition (T5.4 M2) — the dock rail (view). Replaces the fixed sub-tab
// strip when the windowing flag is ON: a horizontal dnd-kit sortable strip of the
// docked panels — click to focus, drag to reorder, × to hide (a hidden panel stays
// MOUNTED, just dropped from the rail; the ComponentPicker re-shows it). Pure view:
// the data + callbacks come from CompositionPanel (which owns the layout dispatch).
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext, horizontalListSortingStrategy, sortableKeyboardCoordinates, useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { WorkspacePanelId } from '../../workspace/types';
import { computeReorder } from '../../workspace/dock';
import { ComponentPicker } from './ComponentPicker';

function SortableTab({ id, active, label, floatLabel, popoutLabel, onSelect, onHide, onFloat, onPopout }: {
  id: WorkspacePanelId; active: boolean; label: string; floatLabel: string; popoutLabel: string;
  onSelect: () => void; onHide: () => void; onFloat: () => void; onPopout: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 };
  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`dock-tab-${id}`}
      className={`group flex shrink-0 items-center gap-1 whitespace-nowrap rounded-t px-2 py-1 ${active ? 'bg-neutral-100 font-medium dark:bg-neutral-800' : 'text-neutral-500'}`}
    >
      <button type="button" data-testid={`dock-select-${id}`} onClick={onSelect} {...attributes} {...listeners}>
        {label}
      </button>
      <button
        type="button" data-testid={`dock-float-${id}`}
        className="text-neutral-400 opacity-0 hover:text-neutral-600 group-hover:opacity-100"
        onClick={onFloat}
        aria-label={floatLabel}
        title={floatLabel}
      >⤢</button>
      <button
        type="button" data-testid={`dock-popout-${id}`}
        className="text-neutral-400 opacity-0 hover:text-neutral-600 group-hover:opacity-100"
        onClick={onPopout}
        aria-label={popoutLabel}
        title={popoutLabel}
      >⮬</button>
      <button
        type="button" data-testid={`dock-hide-${id}`}
        className="text-neutral-400 opacity-0 hover:text-neutral-600 group-hover:opacity-100"
        onClick={onHide}
        aria-label="hide panel"
      >×</button>
    </div>
  );
}

export function DockRail({ visibleIds, hiddenIds, active, onSelect, onReorder, onHide, onShow, onFloat, onPopout, rightSlot }: {
  visibleIds: WorkspacePanelId[];
  hiddenIds: WorkspacePanelId[];
  active: WorkspacePanelId;
  onSelect: (id: WorkspacePanelId) => void;
  onReorder: (ids: WorkspacePanelId[]) => void;
  onHide: (id: WorkspacePanelId) => void;
  onShow: (id: WorkspacePanelId) => void;
  onFloat: (id: WorkspacePanelId) => void;    // M3 — pop the panel into a floating window
  onPopout: (id: WorkspacePanelId) => void;   // M4 — pop the panel into a separate OS window
  rightSlot?: ReactNode;   // e.g. the Power-view trigger — kept available in dock mode
}) {
  const { t } = useTranslation('composition');
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const handleDragEnd = (e: DragEndEvent) => {
    const { active: a, over } = e;
    if (!over || a.id === over.id) return;
    const next = computeReorder(visibleIds, String(a.id), String(over.id));
    if (next !== visibleIds) onReorder(next);
  };

  return (
    <div data-testid="composition-dock-rail" className="flex items-center gap-1 border-b border-neutral-200 px-2 pt-1 text-sm dark:border-neutral-700">
      <div className="flex flex-1 gap-1 overflow-x-auto">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={visibleIds} strategy={horizontalListSortingStrategy}>
            {visibleIds.map((id) => (
              <SortableTab
                key={id} id={id} active={id === active}
                label={t(id, { defaultValue: id })}
                floatLabel={t('dock.float', { defaultValue: 'Float' })}
                popoutLabel={t('dock.popout', { defaultValue: 'Pop out' })}
                onSelect={() => onSelect(id)}
                onHide={() => onHide(id)}
                onFloat={() => onFloat(id)}
                onPopout={() => onPopout(id)}
              />
            ))}
          </SortableContext>
        </DndContext>
      </div>
      <ComponentPicker hiddenIds={hiddenIds} onShow={onShow} />
      {rightSlot}
    </div>
  );
}
