// LOOM Composition (T1.1a) — one committed-outline-tree row (render only).
// Status dot from `status`; the current chapter is highlighted; parents get a
// collapse/expand chevron (a sibling button — no nested-button a11y issue).
import type { OutlineNode } from '../types';

const DOT: Record<OutlineNode['status'], string> = {
  done: '●', drafting: '◐', outline: '○', empty: '○',
};

export function OutlineNodeRow({
  node, depth, hasChildren, expanded, isCurrent, onToggle, onSelect,
}: {
  node: OutlineNode;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
  isCurrent: boolean;
  onToggle: () => void;
  onSelect: () => void;
}) {
  return (
    <div className="flex items-center" style={{ paddingLeft: depth * 14 }}>
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
        <span className="min-w-0 flex-1 truncate">{node.title || node.kind}</span>
      </button>
    </div>
  );
}
