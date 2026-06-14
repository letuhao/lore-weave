// C28 (dị bản M6) — the LIVING-WORLD timeline tree. A world surfaces its canon
// Work as the TRUNK and each dị bản as a BRANCH off it at the chapter-level
// `branch_point` (G3), resolved via C23's `source_work_id` chain among ONLY this
// world's books (no cross-world bleed). REUSES the shared `GraphCanvas` SVG/tree
// layer (LOCKED G5 — NO new graph library): the same canvas that renders the
// scene graph / relationship map / project graph, here fed a hand-rolled
// trunk+branch tree layout.
//
// READ-ONLY navigation: click a node → navigate into that Work (the canon
// writing surface for the trunk, the dị bản studio for a branch — both live in
// the Work's book workspace, since COW keeps a derivative on the source's
// book_id). Navigation is fired from an EXPLICIT click handler (FE rule: never a
// useEffect watching a selected-node). No edit actions on the tree.
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { GraphCanvas, type Pos } from '@/features/composition/components/GraphCanvas';
import { useLivingWorld } from '../hooks/useLivingWorld';
import { layoutWorldTree, type WorldTreeEdge } from '../lib/livingWorldTree';
import { WorldTreeNode, WORLD_NODE_W, WORLD_NODE_H } from './WorldTreeNode';

interface LivingWorldTreeProps {
  worldId: string | undefined;
}

export function LivingWorldTree({ worldId }: LivingWorldTreeProps) {
  const { t } = useTranslation('world');
  const navigate = useNavigate();
  const { tree, isLoading, isError, error, isEmpty } = useLivingWorld(worldId);

  // Per-device drag overrides (no server layout); the deterministic tree layout
  // is the seed.
  const auto = useMemo(() => layoutWorldTree(tree), [tree]);
  const [local, setLocal] = useState<Record<string, Pos>>({});
  const localRef = useRef<Record<string, Pos>>(local);
  const applyLocal = (next: Record<string, Pos>) => {
    localRef.current = next;
    setLocal(next);
  };
  const positions = useMemo(() => {
    const acc: Record<string, Pos> = {};
    for (const n of tree.nodes) acc[n.id] = local[n.id] ?? auto[n.id] ?? { x: 24, y: 24 };
    return acc;
  }, [tree.nodes, local, auto]);

  const byId = useMemo(() => new Map(tree.nodes.map((n) => [n.id, n])), [tree.nodes]);

  // EXPLICIT navigation handler (NOT a useEffect-for-events): click a node → go
  // into that Work's book workspace. Canon → canon writing surface; dị bản →
  // its studio. COW keeps a derivative on the SOURCE's book_id, so a canon + its
  // N dị bản share one bookId — the `?work=<surrogate id>` selector tells the
  // composition panel WHICH Work to open (it seeds activeWorkOverride from it),
  // so clicking a specific branch lands in THAT dị bản's studio, not the canon.
  const openWork = (id: string) => {
    const node = byId.get(id);
    if (!node) return;
    navigate(`/books/${node.bookId}?work=${encodeURIComponent(node.id)}`);
  };

  if (isLoading) {
    return (
      <Hint data-testid="living-world-loading">
        {t('living.loading', { defaultValue: 'Loading the living world…' })}
      </Hint>
    );
  }
  if (isError) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
        data-testid="living-world-error"
      >
        {t('living.loadFailed', {
          defaultValue: 'Failed to load the living world: {{error}}',
          error: error?.message ?? 'unknown',
        })}
      </div>
    );
  }
  if (isEmpty) {
    return (
      <Hint data-testid="living-world-empty">
        {t('living.empty', {
          defaultValue: 'No works in this world yet — start a book or a dị bản to grow its timeline.',
        })}
      </Hint>
    );
  }

  return (
    <div className="flex h-[60vh] flex-col rounded-md border" data-testid="living-world-tree">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="font-medium text-foreground">
          {t('living.title', { defaultValue: 'Living world' })}
        </span>
        <span className="text-muted-foreground" data-testid="living-world-counts">
          {t('living.counts', {
            defaultValue: '{{canon}} canon · {{branches}} dị bản branches',
            canon: tree.trunkCount,
            branches: tree.branchCount,
          })}
        </span>
        <span className="ml-auto text-muted-foreground/70">
          {t('living.hint', {
            defaultValue: 'Scroll to zoom · drag empty space to pan · click a work to open it',
          })}
        </span>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col">
        <GraphCanvas<WorldTreeEdge>
          testid="living-world-svg"
          zoomable
          positions={positions}
          nodeIds={tree.nodes.map((n) => n.id)}
          edges={tree.edges}
          edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
          edgeKey={(e) => e.id}
          nodeSize={{ w: WORLD_NODE_W, h: WORLD_NODE_H }}
          onNodeClick={openWork}
          onNodeDrag={(id, pos) => applyLocal({ ...localRef.current, [id]: pos })}
          onBackgroundClick={() => { /* read-only tree: nothing to clear */ }}
          defs={(
            <marker
              id="living-world-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="#f59e0b" />
            </marker>
          )}
          renderEdge={(e, from, to) => <BranchEdge edge={e} from={from} to={to} />}
          renderNode={(id, h) => {
            const n = byId.get(id);
            if (!n) return null;
            return (
              <WorldTreeNode
                node={n}
                pos={positions[id]}
                onPointerDown={h.onPointerDown}
                // Navigate DIRECTLY from the activate handler (keyboard Enter);
                // the canvas routes a non-drag pointer click through onNodeClick.
                onActivate={() => openWork(id)}
              />
            );
          }}
        />
      </div>
    </div>
  );
}

// A branch connector: an elbow from the source (parent) node to the derivative
// (child), labelled with the branch_point chapter. Render-only.
function BranchEdge({ edge, from, to }: { edge: WorldTreeEdge; from: Pos; to: Pos }) {
  const { t } = useTranslation('world');
  // Anchor at the right edge of the parent and the left edge of the child.
  const x1 = from.x + WORLD_NODE_W;
  const y1 = from.y + WORLD_NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + WORLD_NODE_H / 2;
  const midX = (x1 + x2) / 2;
  const d = `M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`;
  return (
    <g data-testid="branch-edge" data-edge={edge.id}>
      <path d={d} fill="none" stroke="#f59e0b" strokeWidth={1.5} markerEnd="url(#living-world-arrow)" />
      {edge.branchPoint != null && (
        <text x={midX + 4} y={(y1 + y2) / 2 - 4} className="fill-amber-600 text-[9px] dark:fill-amber-400">
          {t('living.edgeLabel', { defaultValue: 'ch. {{ch}}', ch: edge.branchPoint + 1 })}
        </text>
      )}
    </g>
  );
}

const Hint = ({ children, ...rest }: { children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground"
    {...rest}
  >
    {children}
  </div>
);
