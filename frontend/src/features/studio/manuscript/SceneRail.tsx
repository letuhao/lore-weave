// #12 M-C/M-F/M-G · Scene Rail — the scene surface beside the editor. M-C: metadata
// edits (title row status + synopsis) save IMMEDIATELY through composition patchNode
// (OCC If-Match) then reloadScenes — the same domain path the agent's MCP tool uses, so
// Lane B keeps every view consistent. M-F: a scene title click JUMPS the prose to its
// anchored heading (sceneMarker = heading `sceneId` attr); the ⚓ action backfills
// anchors by unique title match (dirties → the user saves). M-G: ＋ create / ✕ archive
// (with Undo via restore) / ▲▼ reorder, all through the existing outline REST.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { cn } from '@/lib/utils';
import { useStudioBusSelector } from '../host/StudioHostProvider';
import { useManuscriptUnit, useManuscriptUnitMeta } from './unit/ManuscriptUnitProvider';

const STATUSES: OutlineNode['status'][] = ['empty', 'outline', 'drafting', 'done'];

interface RowProps {
  scene: OutlineNode;
  active: boolean;
  first: boolean;
  last: boolean;
  /** id of the scene BEFORE my predecessor (▲ target: place after it; null = become first) */
  prevPrevId: string | null;
  /** id of my successor (▼ target: place after it; null = already last) */
  nextId: string | null;
  onSaved: () => void;
  onJump: (sceneId: string) => void;
  onDeleted: (id: string, title: string) => void;
}

function SceneRow({ scene, active, first, last, prevPrevId, nextId, onSaved, onJump, onDeleted }: RowProps) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const [synopsis, setSynopsis] = useState(scene.synopsis);
  const [error, setError] = useState<string | null>(null);
  // 22-C4 (F2) — the title was CREATE-ONLY (a jump button, never an input). Inline edit writes
  // outline_node.title (the spec — never scenes.title, which is a parsed heading, SC1). Single
  // click still jumps; the ✎ affordance opens an input.
  const [titleEditing, setTitleEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState(scene.title);
  const ref = useRef<HTMLDivElement | null>(null);

  // External refresh (Lane B / save-reload) re-seeds the draft — but never over an in-progress edit.
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setSynopsis(scene.synopsis); }, [scene.synopsis]);
  // Re-seed the title draft on external change too, but never over an open title edit.
  useEffect(() => { if (!titleEditing) setTitleDraft(scene.title); }, [scene.title, titleEditing]);

  useEffect(() => {
    if (active) ref.current?.scrollIntoView?.({ block: 'nearest' });
  }, [active]);

  const run = async (fn: () => Promise<unknown>) => {
    if (!accessToken) return;
    setError(null);
    try {
      await fn();
      onSaved();
    } catch (e) {
      const status = (e as { status?: number }).status;
      setError(status === 412 ? t('sceneRail.stale', { defaultValue: 'changed elsewhere — reloaded' }) : (e as Error).message);
      if (status === 412) onSaved(); // pull the fresh version so the next edit lands
    }
  };

  const patch = (p: Partial<OutlineNode>) =>
    run(() => compositionApi.patchNode(scene.id, p, accessToken!, scene.version));
  const commitTitle = () => {
    const next = titleDraft.trim();
    setTitleEditing(false);
    // Only write on a real change; empty title is rejected (a scene must keep a name).
    if (next && next !== scene.title) void patch({ title: next });
    else setTitleDraft(scene.title);
  };
  // ▲ = place after the scene BEFORE my predecessor (null = become first); ▼ = after my successor.
  const moveUp = () =>
    run(() => compositionApi.reorderNode(scene.id, { new_parent_id: scene.parent_id ?? null, after_id: prevPrevId }, accessToken!, scene.version));
  const moveDown = () =>
    run(() => compositionApi.reorderNode(scene.id, { new_parent_id: scene.parent_id ?? null, after_id: nextId }, accessToken!, scene.version));
  const archive = () =>
    run(async () => {
      await compositionApi.archiveNode(scene.id, accessToken!);
      onDeleted(scene.id, scene.title);
    });

  return (
    <div
      ref={ref}
      data-testid={`scene-rail-row-${scene.id}`}
      className={cn('group border-b px-2 py-1.5', active && 'bg-[var(--primary-muted)]')}
    >
      <div className="flex items-center gap-1">
        {titleEditing ? (
          // 22-C4 (F2) inline title edit → outline_node.title. Enter/blur commits, Escape cancels.
          <input
            data-testid={`scene-rail-title-input-${scene.id}`}
            value={titleDraft}
            autoFocus
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={commitTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitTitle();
              if (e.key === 'Escape') { setTitleDraft(scene.title); setTitleEditing(false); }
            }}
            className="min-w-0 flex-1 rounded border bg-background px-1 py-0.5 text-[11px] font-medium"
          />
        ) : (
          <>
            {/* M-F — single click jumps the prose to the anchored heading. */}
            <button
              type="button"
              data-testid={`scene-rail-jump-${scene.id}`}
              onClick={() => onJump(scene.id)}
              className="min-w-0 flex-1 truncate text-left text-[11px] font-medium hover:text-primary"
              title={scene.title}
            >
              {scene.title}
            </button>
            <button
              type="button"
              data-testid={`scene-rail-title-edit-${scene.id}`}
              onClick={() => { setTitleDraft(scene.title); setTitleEditing(true); }}
              className="rounded px-0.5 text-[10px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-focus-within:opacity-100 group-hover:opacity-100"
              aria-label={t('sceneRail.editTitle', { defaultValue: 'Rename scene' })}
            >✎</button>
          </>
        )}
        <select
          data-testid={`scene-rail-status-${scene.id}`}
          value={scene.status}
          onChange={(e) => void patch({ status: e.target.value as OutlineNode['status'] })}
          className="rounded border bg-background px-1 py-0.5 text-[10px] text-muted-foreground"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{t(`sceneRail.status.${s}`, { defaultValue: s })}</option>)}
        </select>
      </div>
      <textarea
        data-testid={`scene-rail-synopsis-${scene.id}`}
        value={synopsis}
        rows={2}
        placeholder={t('sceneRail.synopsisPlaceholder', { defaultValue: 'Synopsis…' })}
        onFocus={() => { editing.current = true; }}
        onChange={(e) => setSynopsis(e.target.value)}
        onBlur={() => {
          editing.current = false;
          if (synopsis !== scene.synopsis) void patch({ synopsis });
        }}
        className="mt-1 w-full resize-none rounded border bg-background px-1.5 py-1 text-[11px] text-muted-foreground focus:text-foreground"
      />
      {/* M-G row actions — quiet until hover (the rail stays scannable). */}
      <div className="mt-0.5 flex items-center gap-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          data-testid={`scene-rail-up-${scene.id}`}
          disabled={first}
          onClick={() => void moveUp()}
          className="rounded border px-1 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-30"
          aria-label={t('sceneRail.moveUp', { defaultValue: 'Move up' })}
        >▲</button>
        <button
          type="button"
          data-testid={`scene-rail-down-${scene.id}`}
          disabled={last}
          onClick={() => void moveDown()}
          className="rounded border px-1 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-30"
          aria-label={t('sceneRail.moveDown', { defaultValue: 'Move down' })}
        >▼</button>
        <button
          type="button"
          data-testid={`scene-rail-delete-${scene.id}`}
          onClick={() => void archive()}
          className="ml-auto rounded border px-1 text-[10px] text-muted-foreground hover:text-destructive"
          aria-label={t('sceneRail.delete', { defaultValue: 'Delete scene' })}
        >✕</button>
      </div>
      {error && <p data-testid={`scene-rail-error-${scene.id}`} className="mt-0.5 text-[10px] text-destructive">{error}</p>}
    </div>
  );
}

export function SceneRail() {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const unit = useManuscriptUnit();
  const meta = useManuscriptUnitMeta();
  const activeSceneId = useStudioBusSelector((s) => s.activeSceneId);
  const [notice, setNotice] = useState<string | null>(null);
  const [undo, setUndo] = useState<{ id: string; title: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  // M-F — a navigator / Quick-Open scene click (bus slice) also jumps the prose.
  const jumpedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!unit || !activeSceneId || jumpedRef.current === activeSceneId) return;
    jumpedRef.current = activeSceneId;
    unit.jumpToScene(activeSceneId);
  }, [unit, activeSceneId]);

  if (!unit) return null;
  const scenes = unit.state.scenes;
  const reload = () => void unit.reloadScenes();

  const onJump = (sceneId: string) => {
    if (!unit.jumpToScene(sceneId)) {
      setNotice(t('sceneRail.notAnchored', { defaultValue: 'Scene not anchored in the text yet — use ⚓ to link headings.' }));
    }
  };

  const onAnchor = () => {
    const r = unit.anchorScenes();
    if (!r) return;
    setNotice(
      r.changed
        ? t('sceneRail.anchored', { count: r.anchored, unmatched: r.unmatched, defaultValue: `Anchored ${r.anchored} scene(s), ${r.unmatched} unmatched — ⌘S to save.` })
        : t('sceneRail.anchorNoop', { count: r.anchored, unmatched: r.unmatched, defaultValue: `${r.anchored} already anchored, ${r.unmatched} without a matching heading.` }),
    );
  };

  const onDeleted = (id: string, title: string) => {
    setUndo({ id, title });
    setNotice(null);
  };

  const onUndoDelete = async () => {
    if (!undo || !accessToken) return;
    try { await compositionApi.restoreNode(undo.id, accessToken); } catch { /* reload below re-syncs either way */ }
    setUndo(null);
    reload();
  };

  const onCreate = async () => {
    const title = newTitle.trim();
    const parentId = unit.state.sceneChapterNodeId;
    const projectId = meta?.projectId;
    if (!title || !parentId || !projectId || !accessToken || !unit.state.chapterId) return;
    try {
      await compositionApi.createNode(
        projectId,
        { kind: 'scene', parent_id: parentId, chapter_id: unit.state.chapterId, title, status: 'empty' },
        accessToken,
      );
      setNewTitle('');
      setAdding(false);
      reload();
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  return (
    <div data-testid="studio-scene-rail" className="flex h-full w-56 flex-shrink-0 flex-col border-l">
      <div className="flex h-7 flex-shrink-0 items-center gap-1 border-b px-2 text-[11px] font-medium text-muted-foreground">
        {t('sceneRail.title', { defaultValue: 'Scenes' })}
        <span className="text-muted-foreground/60">{scenes.length}</span>
        {scenes.length > 0 && (
          <button
            type="button"
            data-testid="scene-rail-anchor"
            onClick={onAnchor}
            title={t('sceneRail.anchorTitle', { defaultValue: 'Link scenes to their headings in the text' })}
            className="ml-auto rounded px-1 hover:bg-secondary hover:text-foreground"
          >⚓</button>
        )}
        <button
          type="button"
          data-testid="scene-rail-add"
          disabled={!unit.state.sceneChapterNodeId}
          onClick={() => setAdding((v) => !v)}
          title={unit.state.sceneChapterNodeId
            ? t('sceneRail.add', { defaultValue: 'Add scene' })
            : t('sceneRail.addDisabled', { defaultValue: 'Chapter has no outline yet (create it in the composer)' })}
          className={cn('rounded px-1 hover:bg-secondary hover:text-foreground disabled:opacity-30', scenes.length === 0 && 'ml-auto')}
        >＋</button>
      </div>
      {adding && (
        <div className="flex items-center gap-1 border-b px-2 py-1">
          <input
            data-testid="scene-rail-new-title"
            value={newTitle}
            autoFocus
            placeholder={t('sceneRail.newTitlePlaceholder', { defaultValue: 'Scene title…' })}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void onCreate(); if (e.key === 'Escape') setAdding(false); }}
            className="min-w-0 flex-1 rounded border bg-background px-1.5 py-0.5 text-[11px]"
          />
          <button type="button" data-testid="scene-rail-create" onClick={() => void onCreate()} className="rounded border px-1.5 py-0.5 text-[10px] hover:bg-secondary">
            {t('sceneRail.create', { defaultValue: 'Add' })}
          </button>
        </div>
      )}
      {notice && (
        <p data-testid="scene-rail-notice" className="border-b px-2 py-1 text-[10px] text-muted-foreground">
          {notice}
          <button type="button" className="ml-1 underline" onClick={() => setNotice(null)}>×</button>
        </p>
      )}
      {undo && (
        <p data-testid="scene-rail-undo" className="border-b px-2 py-1 text-[10px] text-muted-foreground">
          {t('sceneRail.deleted', { title: undo.title, defaultValue: `Deleted "${undo.title}".` })}
          <button type="button" data-testid="scene-rail-undo-btn" className="ml-1 underline" onClick={() => void onUndoDelete()}>
            {t('sceneRail.undo', { defaultValue: 'Undo' })}
          </button>
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        {scenes.length === 0 ? (
          <p className="p-3 text-center text-[11px] text-muted-foreground">
            {t('sceneRail.empty', { defaultValue: 'No scenes for this chapter (outline it in the composer).' })}
          </p>
        ) : (
          scenes.map((s, i) => (
            <SceneRow
              key={s.id}
              scene={s}
              active={s.id === activeSceneId}
              first={i === 0}
              last={i === scenes.length - 1}
              prevPrevId={scenes[i - 2]?.id ?? null}
              nextId={scenes[i + 1]?.id ?? null}
              onSaved={reload}
              onJump={onJump}
              onDeleted={onDeleted}
            />
          ))
        )}
      </div>
    </div>
  );
}
