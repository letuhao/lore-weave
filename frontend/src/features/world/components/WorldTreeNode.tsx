// C28 (dị bản M6) — one node in the living-world timeline tree: a composition
// Work, badged canon (trunk) vs dị bản (branch). Render-only; self-positions
// (GraphCanvas does NOT transform it). The body is the click target (→ navigate
// into the Work) AND the drag handle. A branch shows its branch_point label so
// the tree reads as a navigable "what-if map". READ-ONLY: no edit affordance.
import { useTranslation } from 'react-i18next';
import { GitBranch, BookOpen } from 'lucide-react';
import type { Pos } from '@/features/composition/components/GraphCanvas';
import type { WorldTreeNode as TreeNode } from '../lib/livingWorldTree';

export const WORLD_NODE_W = 184;
export const WORLD_NODE_H = 54;

export function WorldTreeNode({
  node,
  pos,
  onPointerDown,
  onActivate,
}: {
  node: TreeNode;
  pos: Pos;
  onPointerDown: (e: React.PointerEvent) => void;
  onActivate: () => void;
}) {
  const { t } = useTranslation('world');
  const isCanon = node.isCanon;
  const label = isCanon
    ? t('living.canonBadge', { defaultValue: 'Canon' })
    : t('living.branchBadge', { defaultValue: 'Dị bản' });

  return (
    <g
      transform={`translate(${pos.x}, ${pos.y})`}
      data-testid="world-tree-node"
      data-work={node.id}
      data-canon={isCanon ? 'true' : 'false'}
    >
      <foreignObject width={WORLD_NODE_W} height={WORLD_NODE_H} style={{ overflow: 'visible' }}>
        <div
          data-testid="world-tree-node-body"
          role="button"
          tabIndex={0}
          aria-label={
            isCanon
              ? t('living.canonAria', { defaultValue: 'Canon: {{title}}', title: node.bookTitle })
              : t('living.branchAria', {
                  defaultValue: 'Dị bản branching at chapter {{ch}}: {{title}}',
                  ch: (node.branchPoint ?? 0) + 1,
                  title: node.bookTitle,
                })
          }
          onPointerDown={onPointerDown}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onActivate();
            }
          }}
          className={
            'flex h-full cursor-grab select-none flex-col justify-center gap-0.5 rounded-md border bg-card px-2 py-1 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-primary active:cursor-grabbing ' +
            (isCanon ? 'border-primary/60 ' : 'border-amber-500/60 ')
          }
        >
          <span className="flex items-center gap-1 text-[11px]">
            {isCanon ? (
              <BookOpen className="h-3 w-3 shrink-0 text-primary" aria-hidden />
            ) : (
              <GitBranch className="h-3 w-3 shrink-0 text-amber-500" aria-hidden />
            )}
            <span
              className={
                'shrink-0 rounded px-1 text-[9px] font-semibold uppercase tracking-wide ' +
                (isCanon ? 'bg-primary/10 text-primary' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400')
              }
              data-testid="world-tree-node-badge"
            >
              {label}
            </span>
          </span>
          <span className="min-w-0 truncate text-[12px] font-medium" title={node.bookTitle}>
            {node.bookTitle}
          </span>
          {!isCanon && (
            <span className="truncate text-[10px] text-muted-foreground" data-testid="world-tree-node-branchpoint">
              {t('living.branchAt', {
                defaultValue: 'branches at ch. {{ch}}',
                ch: (node.branchPoint ?? 0) + 1,
              })}
              {node.orphanSource && (
                <span className="ml-1 text-amber-600 dark:text-amber-400" data-testid="world-tree-node-orphan">
                  {t('living.orphan', { defaultValue: '· source outside this world' })}
                </span>
              )}
            </span>
          )}
        </div>
      </foreignObject>
    </g>
  );
}
