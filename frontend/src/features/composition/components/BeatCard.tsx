// LOOM Composition (T1.2) — one Beat Sheet card (a structure-template beat) plus
// the shared NodeChip (a draggable scene/chapter token with a status dot, a
// jump-to button, an a11y <select> to (re)assign its beat, and — inside a card —
// an unmap ✕). The card is a drop target (`beat:<key>`); dropping a node on it
// assigns node.beat_role = key. Render-only; assigns/navigation bubble up.
import { useTranslation } from 'react-i18next';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import type { Beat, OutlineNode } from '../types';

const DOT: Record<OutlineNode['status'], string> = {
  done: '●', drafting: '◐', outline: '○', empty: '○',
};

export type BeatFill = 'drafted' | 'writing' | 'empty' | 'unplaced';

export function NodeChip({
  node, beatKeys, draggable, showUnmap, onNavigate, onAssign,
}: {
  node: OutlineNode;
  beatKeys: string[];
  draggable: boolean;
  showUnmap: boolean;
  onNavigate: (node: OutlineNode) => void;
  onAssign: (node: OutlineNode, beatKey: string | null) => void;
}) {
  const { t } = useTranslation('composition');
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: node.id, disabled: !draggable });
  return (
    <div
      ref={setNodeRef}
      data-testid="beat-node-chip"
      data-kind={node.kind}
      className={'flex items-center gap-1 rounded border bg-background px-1.5 py-0.5 text-[11px] ' + (isDragging ? 'opacity-50' : '')}
    >
      {draggable && (
        <button
          type="button"
          data-testid="beat-node-drag"
          aria-label={t('outline.drag', { defaultValue: 'Drag to reorder' })}
          className="cursor-grab text-[10px] text-muted-foreground hover:text-foreground active:cursor-grabbing"
          {...attributes}
          {...listeners}
        >
          ⠿
        </button>
      )}
      <span className="text-muted-foreground" aria-hidden>{DOT[node.status]}</span>
      <button
        type="button"
        data-testid="beat-node-open"
        className="min-w-0 flex-1 truncate text-left hover:text-primary"
        onClick={() => onNavigate(node)}
      >
        {node.title || node.kind}
      </button>
      <select
        data-testid="beat-node-select"
        aria-label={t('beatsheet.assign', { defaultValue: 'Assign beat' })}
        className="max-w-[5rem] rounded border bg-background text-[10px]"
        // A beat_role not in THIS template (a stale key after a template switch)
        // shows as "none" — it has no matching option and is treated as unmapped.
        value={node.beat_role && beatKeys.includes(node.beat_role) ? node.beat_role : ''}
        onChange={(e) => onAssign(node, e.target.value || null)}
      >
        <option value="">{t('beatsheet.none', { defaultValue: '— none —' })}</option>
        {beatKeys.map((k) => <option key={k} value={k}>{k}</option>)}
      </select>
      {showUnmap && (
        <button
          type="button"
          data-testid="beat-node-unmap"
          aria-label={t('beatsheet.unmap', { defaultValue: 'Unmap' })}
          className="text-[10px] text-muted-foreground hover:text-destructive"
          onClick={() => onAssign(node, null)}
        >
          ✕
        </button>
      )}
    </div>
  );
}

export function BeatCard({
  beat, nodes, state, beatKeys, draggable, onNavigate, onAssign,
}: {
  beat: Beat;
  nodes: OutlineNode[];
  state: BeatFill;
  beatKeys: string[];
  draggable: boolean;
  onNavigate: (node: OutlineNode) => void;
  onAssign: (node: OutlineNode, beatKey: string | null) => void;
}) {
  const { t } = useTranslation('composition');
  const { setNodeRef, isOver } = useDroppable({ id: `beat:${beat.key}` });
  return (
    <div
      ref={setNodeRef}
      data-testid="beat-card"
      data-beat={beat.key}
      data-state={state}
      title={beat.purpose}
      className={'flex w-48 flex-col gap-1 rounded-md border p-2 text-xs ' + (isOver ? 'border-primary bg-primary/[0.06] ' : 'bg-card ')}
    >
      <div className="flex items-center justify-between">
        <span className="truncate font-medium">{beat.key}</span>
        <span data-testid="beat-state" className="shrink-0 text-[10px] text-muted-foreground">
          {t(`beatsheet.state_${state}`, { defaultValue: state })}
        </span>
      </div>
      {nodes.length === 0 ? (
        <span className="text-[11px] italic text-muted-foreground/60">{t('beatsheet.unplaced', { defaultValue: 'unplaced' })}</span>
      ) : (
        <div className="flex flex-col gap-1">
          {nodes.map((n) => (
            <NodeChip
              key={n.id}
              node={n}
              beatKeys={beatKeys}
              draggable={draggable}
              showUnmap
              onNavigate={onNavigate}
              onAssign={onAssign}
            />
          ))}
        </div>
      )}
    </div>
  );
}
