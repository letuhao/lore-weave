// LOOM Composition (T1.2) — Beat Sheet: a structure template's beats as cards,
// each showing the scene/chapter node(s) mapped to it (node.beat_role == beat.key)
// + a fill-state, so the author sees coverage. Drag a node onto a beat card to
// assign its beat_role (or onto the Unmapped zone to clear); a per-node <select>
// is the a11y fallback. Reuses useStructureTemplates + useOutline + the shared
// setBeatRole mutation. BE delta: none beyond the chapter-beat_role migration.
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useDroppable, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { useStructureTemplates } from '../hooks/usePlanner';
import { useOutline, useOutlineMutations } from '../hooks/useOutline';
import { BeatCard, NodeChip, type BeatFill } from './BeatCard';
import type { OutlineNode, StructureTemplate } from '../types';

export type BeatEntry = { beat: { key: string; purpose: string }; nodes: OutlineNode[]; state: BeatFill };

function fillState(nodes: OutlineNode[]): BeatFill {
  if (nodes.length === 0) return 'unplaced';
  if (nodes.every((n) => n.status === 'done')) return 'drafted';
  if (nodes.some((n) => n.status === 'drafting' || n.status === 'done')) return 'writing';
  return 'empty';
}

// Pure (exported for tests): join the template's beats to the nodes by
// `beat.key == node.beat_role`. Only active scene/chapter nodes participate. A
// node with no beat_role — OR a beat_role not in THIS template (template switch
// re-keys) — is `unmapped`. Beats keep template order; each gets a fill-state.
export function buildBeatSheet(
  template: StructureTemplate | null,
  nodes: OutlineNode[],
): { beats: BeatEntry[]; unmapped: OutlineNode[] } {
  if (!template) return { beats: [], unmapped: [] };
  const keys = new Set(template.beats.map((b) => b.key));
  const byBeat = new Map<string, OutlineNode[]>();
  const unmapped: OutlineNode[] = [];
  for (const n of nodes) {
    if (n.is_archived || (n.kind !== 'scene' && n.kind !== 'chapter')) continue;
    if (n.beat_role && keys.has(n.beat_role)) {
      const arr = byBeat.get(n.beat_role);
      if (arr) arr.push(n); else byBeat.set(n.beat_role, [n]);
    } else {
      unmapped.push(n);
    }
  }
  const beats = template.beats.map((beat) => {
    const ns = byBeat.get(beat.key) ?? [];
    return { beat, nodes: ns, state: fillState(ns) };
  });
  return { beats, unmapped };
}

function UnmapZone({ children }: { children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'unmap' });
  return (
    <div ref={setNodeRef} data-testid="beat-unmap-zone" className={'rounded-md border border-dashed p-2 ' + (isOver ? 'border-primary bg-primary/[0.06]' : '')}>
      {children}
    </div>
  );
}

export function BeatSheetView({ bookId, projectId, token }: { bookId: string; projectId: string | undefined; token: string | null }) {
  const { t } = useTranslation('composition');
  const navigate = useNavigate();
  const templates = useStructureTemplates(token);
  const q = useOutline(projectId, token);
  const m = useOutlineMutations(projectId, token);
  const [templateId, setTemplateId] = useState<string>('');

  const list = templates.data ?? [];
  const template = useMemo(() => list.find((tpl) => tpl.id === templateId) ?? null, [list, templateId]);
  const nodes = q.data ?? [];
  const { beats, unmapped } = useMemo(() => buildBeatSheet(template, nodes), [template, nodes]);
  const beatKeys = template?.beats.map((b) => b.key) ?? [];

  const onError = (e: unknown) => {
    if ((e as { status?: number }).status === 412) m.invalidate();
  };
  const assign = (node: OutlineNode, beatRole: string | null) => {
    if ((node.beat_role ?? null) === beatRole) return; // no-op
    m.setBeatRole.mutate({ nodeId: node.id, beatRole, version: node.version }, { onError });
  };
  const navigateTo = (node: OutlineNode) => { if (node.chapter_id) navigate(`/books/${bookId}/chapters/${node.chapter_id}/edit`); };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const handleDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over) return;
    const node = nodes.find((n) => n.id === String(active.id));
    if (!node) return;
    const overId = String(over.id);
    if (overId === 'unmap') assign(node, null);
    else if (overId.startsWith('beat:')) assign(node, overId.slice(5));
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden" data-testid="composition-beats">
      <div className="flex flex-shrink-0 items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">{t('beatsheet.title', { defaultValue: 'Beat Sheet' })}</span>
        <select
          data-testid="beats-template-select"
          aria-label={t('beatsheet.pickTemplate', { defaultValue: 'Pick a template' })}
          className="rounded border bg-background px-1 py-0.5"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
        >
          <option value="">{t('beatsheet.pickTemplate', { defaultValue: 'Pick a template…' })}</option>
          {list.map((tpl) => <option key={tpl.id} value={tpl.id}>{tpl.name}</option>)}
        </select>
      </div>

      {!template ? (
        <div data-testid="beats-empty" className="p-3 text-xs text-muted-foreground">
          {t('beatsheet.empty', { defaultValue: 'Pick a structure template to see its beats and your coverage.' })}
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <div className="flex-1 overflow-y-auto p-2">
            <div className="flex flex-wrap gap-2">
              {beats.map((entry) => (
                <BeatCard
                  key={entry.beat.key}
                  beat={entry.beat}
                  nodes={entry.nodes}
                  state={entry.state}
                  beatKeys={beatKeys}
                  draggable
                  onNavigate={navigateTo}
                  onAssign={assign}
                />
              ))}
            </div>
            <div className="mt-3">
              <div className="mb-1 text-[11px] font-medium text-muted-foreground">
                {t('beatsheet.unmapped', { defaultValue: 'Unmapped' })} ({unmapped.length})
              </div>
              <UnmapZone>
                {unmapped.length === 0 ? (
                  <span className="text-[11px] italic text-muted-foreground/60">{t('beatsheet.allMapped', { defaultValue: 'Everything is placed.' })}</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {unmapped.map((n) => (
                      <NodeChip key={n.id} node={n} beatKeys={beatKeys} draggable showUnmap={false} onNavigate={navigateTo} onAssign={assign} />
                    ))}
                  </div>
                )}
              </UnmapZone>
            </div>
          </div>
        </DndContext>
      )}
    </div>
  );
}
