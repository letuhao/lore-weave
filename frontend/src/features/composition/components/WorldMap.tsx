// LOOM Composition (T2.5) — World Map: the book's places (location entities) and
// their location↔location connections as a hand-rolled SVG graph (reuses the shared
// <GraphCanvas> + RelationEdge). Drag to arrange (persisted server-side per work);
// optional backdrop image behind the nodes. "+ add place" / "link places" author the
// knowledge graph; clicking a place opens it in the Cast codex. Render-only; logic in
// useWorldMap.
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { GraphCanvas } from './GraphCanvas';
import { PlaceNode, PLACE_NODE_H, PLACE_NODE_W } from './PlaceNode';
import { RelationEdge } from './RelationEdge';
import { PLACE_LINK_PREDICATES, useWorldMap, type PlaceLinkPredicate } from '../hooks/useWorldMap';
import type { GraphEdge } from '../hooks/useRelationshipMap';
import type { Work } from '../types';

export function WorldMap({
  work, bookId, chapterId, token, onViewCast,
}: {
  work: Work;
  bookId: string;
  chapterId: string;
  token: string | null;
  onViewCast: (name: string) => void;
}) {
  const { t } = useTranslation('composition');
  const wm = useWorldMap(work, bookId, chapterId, token);

  const [newPlace, setNewPlace] = useState('');
  const [linkMode, setLinkMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [predicate, setPredicate] = useState<PlaceLinkPredicate>('borders');
  const fileRef = useRef<HTMLInputElement>(null);

  const byId = useMemo(() => new Map(wm.nodes.map((n) => [n.id, n])), [wm.nodes]);

  const toggleSelect = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-2)));
  const clearSel = () => setSelected([]);
  const toggleLinkMode = () => { setLinkMode((m) => !m); setSelected([]); };

  // Click semantics: in link mode → pick endpoints; otherwise → open in the codex.
  const onNodeActivate = (id: string) => {
    if (linkMode) { toggleSelect(id); return; }
    const n = byId.get(id);
    if (n) onViewCast(n.name);
  };

  // Destructive: confirm, then soft-archive the location entity. On success the
  // places query invalidates and the node drops out on refetch; onError surfaces
  // a toast (never a silent failure).
  const onDeletePlace = (id: string) => {
    const n = byId.get(id);
    if (!n) return;
    const ok = window.confirm(
      t('wmap.deleteConfirm', {
        name: n.name,
        defaultValue: 'Remove “{{name}}” from the world map? This archives the place.',
      }),
    );
    if (!ok) return;
    wm.deletePlace.mutate(id, {
      onError: () => toast.error(t('wmap.deleteFailed', { defaultValue: 'Could not remove the place.' })),
    });
  };

  const addPlace = () => {
    const name = newPlace.trim();
    if (!name) return;
    wm.createPlace.mutate(name, {
      onSuccess: () => setNewPlace(''),
      onError: () => toast.error(t('wmap.addFailed', { defaultValue: 'Could not add the place.' })),
    });
  };

  const doLink = () => {
    if (selected.length !== 2) return;
    wm.linkPlaces.mutate(
      { subjectId: selected[0], objectId: selected[1], predicate },
      {
        onSuccess: () => setSelected([]),
        onError: (e) => {
          const status = (e as { status?: number }).status;
          toast.error(status === 409
            ? t('wmap.linkMissing', { defaultValue: 'One of those places no longer exists.' })
            : t('wmap.linkFailed', { defaultValue: 'Could not link the places.' }));
        },
      },
    );
  };

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) wm.uploadBackdrop.mutate(f);
    e.target.value = '';
  };

  const showToolbar = !wm.projectLoading && !wm.placesLoading && !!wm.knowledgeProjectId;

  return (
    <div className="flex h-full flex-col" data-testid="composition-worldmap">
      {showToolbar && (
        <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
          <span className="text-muted-foreground">{t('wmap.title', { defaultValue: 'World Map' })}</span>
          <input
            data-testid="worldmap-add-input"
            aria-label={t('wmap.add_place', { defaultValue: 'New place name' })}
            placeholder={t('wmap.add_place', { defaultValue: 'New place…' })}
            className="w-28 rounded border bg-background px-1.5 py-0.5"
            value={newPlace}
            onChange={(e) => setNewPlace(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addPlace(); }}
          />
          <button
            type="button" data-testid="worldmap-add"
            className="rounded border px-2 py-0.5 disabled:opacity-50"
            disabled={!newPlace.trim() || wm.createPlace.isPending}
            onClick={addPlace}
          >
            + {t('wmap.add', { defaultValue: 'Place' })}
          </button>
          <button
            type="button" data-testid="worldmap-link-toggle"
            aria-pressed={linkMode}
            className={'rounded border px-2 py-0.5 ' + (linkMode ? 'border-primary text-primary' : '')}
            onClick={toggleLinkMode}
          >
            {t('wmap.link', { defaultValue: 'Link places' })}
          </button>
          {linkMode && (
            selected.length < 2 ? (
              <span className="text-muted-foreground/70">
                {t('wmap.linking', { defaultValue: 'Click two places to link ({{n}}/2)', n: selected.length })}
              </span>
            ) : (
              <span className="flex items-center gap-1" data-testid="worldmap-linkbar">
                <select
                  data-testid="worldmap-predicate"
                  aria-label={t('wmap.predicate', { defaultValue: 'Link kind' })}
                  className="rounded border bg-background px-1 py-0.5"
                  value={predicate}
                  onChange={(e) => setPredicate(e.target.value as PlaceLinkPredicate)}
                >
                  {PLACE_LINK_PREDICATES.map((p) => (
                    <option key={p} value={p}>{t(`wmap.pred_${p}`, { defaultValue: p })}</option>
                  ))}
                </select>
                <button
                  type="button" data-testid="worldmap-link-confirm"
                  className="rounded bg-primary px-2 py-0.5 text-primary-foreground disabled:opacity-50"
                  disabled={wm.linkPlaces.isPending}
                  onClick={doLink}
                >
                  + {t('wmap.link_confirm', { defaultValue: 'link' })}
                </button>
                <button type="button" data-testid="worldmap-link-cancel" className="rounded px-2 py-0.5 text-muted-foreground" onClick={clearSel}>
                  {t('wmap.cancel', { defaultValue: 'Cancel' })}
                </button>
              </span>
            )
          )}
          <span className="ml-auto">
            <input ref={fileRef} type="file" accept="image/*" className="hidden" data-testid="worldmap-backdrop-input" onChange={onPickFile} />
            {/* S7-3 §4.3 — the backdrop upload needs a chapter media bucket (uploadChapterMedia is
                chapter-scoped). On the legacy page a chapter is always open, so this never mattered;
                in the standalone place-graph dock panel `chapterId` can be empty and an upload against
                '' 404s. Degrade gracefully: disable + hint when there's no chapter. Backward-compatible
                (legacy always passes a real chapterId, so its behavior is unchanged). */}
            <button
              type="button" data-testid="worldmap-backdrop"
              className="rounded border px-2 py-0.5 disabled:opacity-50"
              disabled={!chapterId || wm.uploadBackdrop.isPending}
              title={!chapterId
                ? t('wmap.backdropNoChapter', { defaultValue: 'Open a chapter to set a backdrop.' })
                : undefined}
              onClick={() => fileRef.current?.click()}
            >
              {wm.uploadBackdrop.isPending
                ? t('wmap.uploading', { defaultValue: 'Uploading…' })
                : t('wmap.backdrop', { defaultValue: 'Backdrop' })}
            </button>
          </span>
        </div>
      )}

      {wm.projectLoading || wm.placesLoading ? (
        <Hint>{t('wmap.loading', { defaultValue: 'Loading world map…' })}</Hint>
      ) : !wm.knowledgeProjectId ? (
        <Hint>{t('wmap.noProject', { defaultValue: 'No knowledge graph yet — extract this book to populate places.' })}</Hint>
      ) : wm.nodes.length === 0 ? (
        <Hint testid="worldmap-empty">{t('wmap.empty', { defaultValue: 'No places yet — add one above, or extract this book to discover locations.' })}</Hint>
      ) : (
        <GraphCanvas<GraphEdge>
          testid="worldmap-svg"
          positions={wm.positions}
          nodeIds={wm.nodes.map((n) => n.id)}
          edges={wm.edges}
          edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
          edgeKey={(e) => e.id}
          nodeSize={{ w: PLACE_NODE_W, h: PLACE_NODE_H }}
          onNodeClick={onNodeActivate}
          onNodeDrag={(id, pos) => wm.applyLocal({ ...wm.localRef.current, [id]: pos })}
          onNodeDragEnd={() => wm.persistPositions(wm.localRef.current)}
          onBackgroundClick={clearSel}
          background={wm.backdropUrl ? (
            <image
              data-testid="worldmap-backdrop-img"
              href={wm.backdropUrl}
              x={0} y={0} width="100%" height="100%"
              preserveAspectRatio="xMidYMid slice"
              opacity={0.45}
              style={{ pointerEvents: 'none' }}
            />
          ) : undefined}
          defs={(
            <marker id="relmap-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
            </marker>
          )}
          renderEdge={(e, from, to) => <RelationEdge edge={e} from={from} to={to} />}
          renderNode={(id, h) => (
            <PlaceNode
              node={byId.get(id)!}
              pos={wm.positions[id]}
              selected={selected.includes(id)}
              onPointerDown={h.onPointerDown}
              onActivate={() => onNodeActivate(id)}
              onDelete={() => onDeletePlace(id)}
              deleteLabel={t('wmap.delete', { name: byId.get(id)!.name, defaultValue: 'Remove {{name}}' })}
            />
          )}
        />
      )}
    </div>
  );
}

const Hint = ({ children, testid }: { children: React.ReactNode; testid?: string }) => (
  <div data-testid={testid} className="p-3 text-xs text-muted-foreground">{children}</div>
);
