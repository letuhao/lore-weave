// LOOM Composition (T1.1a/b) — one committed-outline-tree row (render only).
// Status dot from `status`; the current chapter is highlighted; parents get a
// collapse/expand chevron (a sibling button — no nested-button a11y issue).
// T1.1b adds a hover-revealed action cluster (rename / add-child / archive /
// status-cycle) + an inline rename input. The actions are siblings of the select
// button (still no nested buttons) and are always mounted (opacity, not
// conditional unmount) so a11y + tests can reach them.
import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { OutlineNode } from '../types';

const DOT: Record<OutlineNode['status'], string> = {
  done: '●', drafting: '◐', outline: '○', empty: '○',
};

// Scene status-cycle order (T1.1b). Advisory; 'done' routes through the BE
// commit-aware path (M9) — same as marking a scene done in the panel.
const STATUS_CYCLE: OutlineNode['status'][] = ['empty', 'outline', 'drafting', 'done'];
const nextStatus = (s: OutlineNode['status']): OutlineNode['status'] =>
  STATUS_CYCLE[(STATUS_CYCLE.indexOf(s) + 1) % STATUS_CYCLE.length];

export function OutlineNodeRow({
  node, depth, hasChildren, expanded, isCurrent, editing,
  onToggle, onSelect, onRenameStart, onRenameCommit, onRenameCancel, onAddChild, onArchive, onCycleStatus, onRestore,
}: {
  node: OutlineNode;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
  isCurrent: boolean;
  editing: boolean;
  onToggle: () => void;
  onSelect: () => void;
  onRenameStart: () => void;
  onRenameCommit: (title: string) => void;
  onRenameCancel: () => void;
  onAddChild: (kind: 'scene' | 'beat') => void;
  onArchive: () => void;
  onCycleStatus: (status: OutlineNode['status']) => void;
  onRestore: () => void;
}) {
  const { t } = useTranslation('composition');
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Idempotency latch: Enter (or blur) commits AND unmounts the input; in real
  // browsers the unmount fires a focusout → onBlur a second time. `done` makes
  // commit/cancel fire-once per edit session; the ref callback resets it each
  // time the input mounts (a fresh edit).
  const done = useRef(false);
  const finish = (fn: () => void) => {
    if (done.current) return;
    done.current = true;
    fn();
  };
  // chapter → add a scene; scene → add a beat; arc/beat have no add-child.
  const childKind: 'scene' | 'beat' | null =
    node.kind === 'chapter' ? 'scene' : node.kind === 'scene' ? 'beat' : null;

  const commit = () => finish(() => {
    const v = inputRef.current?.value.trim() ?? '';
    if (v && v !== node.title) onRenameCommit(v);
    else onRenameCancel();
  });
  const cancel = () => finish(onRenameCancel);

  return (
    <div
      className={'group flex items-center' + (node.is_archived ? ' opacity-45' : '')}
      style={{ paddingLeft: depth * 14 }}
    >
      {hasChildren ? (
        <button
          type="button"
          data-testid="outline-toggle"
          aria-label={expanded ? 'collapse' : 'expand'}
          aria-expanded={expanded}
          className="w-4 shrink-0 text-[10px] text-muted-foreground hover:text-foreground"
          onClick={onToggle}
        >
          {expanded ? '▾' : '▸'}
        </button>
      ) : (
        <span className="w-4 shrink-0" />
      )}

      {editing ? (
        <input
          ref={(el) => { inputRef.current = el; if (el) done.current = false; }}
          data-testid="outline-rename-input"
          defaultValue={node.title}
          autoFocus
          aria-label={t('outline.rename', { defaultValue: 'Rename' })}
          className="min-w-0 flex-1 rounded border bg-background px-1.5 py-0.5 text-xs"
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); commit(); }
            else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
          }}
          onBlur={commit}
        />
      ) : (
        <button
          type="button"
          data-testid="outline-node"
          data-kind={node.kind}
          data-status={node.status}
          onClick={onSelect}
          className={
            'flex min-w-0 flex-1 items-center gap-1.5 px-1.5 py-1 text-left text-xs transition-colors ' +
            (isCurrent
              ? 'border-l-2 border-l-primary bg-primary/[0.07] text-primary'
              : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground')
          }
        >
          <span className="w-3 text-center opacity-70" aria-hidden>{DOT[node.status]}</span>
          <span className={'min-w-0 flex-1 truncate' + (node.is_archived ? ' line-through' : '')}>{node.title || node.kind}</span>
        </button>
      )}

      {!editing && node.is_archived && (
        <div className="flex shrink-0 items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            data-testid="outline-action-restore"
            title={t('outline.restore', { defaultValue: 'Restore' })}
            aria-label={t('outline.restore', { defaultValue: 'Restore' })}
            className="px-1 text-[10px] text-muted-foreground hover:text-foreground"
            onClick={onRestore}
          >
            ↺
          </button>
        </div>
      )}

      {!editing && !node.is_archived && (
        <div className="flex shrink-0 items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          {node.kind === 'scene' && (
            <button
              type="button"
              data-testid="outline-action-status"
              title={t('outline.cycleStatus', { defaultValue: 'Cycle status' })}
              aria-label={t('outline.cycleStatus', { defaultValue: 'Cycle status' })}
              className="px-1 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => onCycleStatus(nextStatus(node.status))}
            >
              ◔
            </button>
          )}
          {childKind && (
            <button
              type="button"
              data-testid="outline-action-addchild"
              title={t(childKind === 'scene' ? 'outline.addScene' : 'outline.addBeat', { defaultValue: 'Add' })}
              aria-label={t(childKind === 'scene' ? 'outline.addScene' : 'outline.addBeat', { defaultValue: 'Add' })}
              className="px-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => onAddChild(childKind)}
            >
              ＋
            </button>
          )}
          <button
            type="button"
            data-testid="outline-action-rename"
            title={t('outline.rename', { defaultValue: 'Rename' })}
            aria-label={t('outline.rename', { defaultValue: 'Rename' })}
            className="px-1 text-[10px] text-muted-foreground hover:text-foreground"
            onClick={onRenameStart}
          >
            ✎
          </button>
          <button
            type="button"
            data-testid="outline-action-archive"
            title={t('outline.archive', { defaultValue: 'Archive' })}
            aria-label={t('outline.archive', { defaultValue: 'Archive' })}
            className="px-1 text-[10px] text-muted-foreground hover:text-destructive"
            onClick={onArchive}
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
