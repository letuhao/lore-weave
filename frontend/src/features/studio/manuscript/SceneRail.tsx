// #12 M-C · Scene Rail — the metadata-first scene surface (R1: no prose anchoring exists; the
// scene layer becomes REAL as an editable outline rail beside the editor). Reads the hoist's
// scenes[] buffer; the bus `scene` slice (navigator/Quick-Open click) highlights + scrolls.
// Edits save IMMEDIATELY through composition patchNode (OCC If-Match) then reloadScenes —
// the same domain path the agent's MCP tool uses, so Lane B keeps every view consistent.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { cn } from '@/lib/utils';
import { useStudioBusSelector } from '../host/StudioHostProvider';
import { useManuscriptUnit } from './unit/ManuscriptUnitProvider';

const STATUSES: OutlineNode['status'][] = ['empty', 'outline', 'drafting', 'done'];

function SceneRow({ scene, active, onSaved }: { scene: OutlineNode; active: boolean; onSaved: () => void }) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const [synopsis, setSynopsis] = useState(scene.synopsis);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  // External refresh (Lane B / save-reload) re-seeds the draft — but never over an in-progress edit.
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setSynopsis(scene.synopsis); }, [scene.synopsis]);

  useEffect(() => {
    if (active) ref.current?.scrollIntoView?.({ block: 'nearest' });
  }, [active]);

  const patch = async (p: Partial<OutlineNode>) => {
    if (!accessToken) return;
    setError(null);
    try {
      await compositionApi.patchNode(scene.id, p, accessToken, scene.version);
      onSaved();
    } catch (e) {
      const status = (e as { status?: number }).status;
      setError(status === 412 ? t('sceneRail.stale', { defaultValue: 'changed elsewhere — reloaded' }) : (e as Error).message);
      if (status === 412) onSaved(); // pull the fresh version so the next edit lands
    }
  };

  return (
    <div
      ref={ref}
      data-testid={`scene-rail-row-${scene.id}`}
      className={cn('border-b px-2 py-1.5', active && 'bg-[var(--primary-muted)]')}
    >
      <div className="flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium" title={scene.title}>{scene.title}</span>
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
      {error && <p data-testid={`scene-rail-error-${scene.id}`} className="mt-0.5 text-[10px] text-destructive">{error}</p>}
    </div>
  );
}

export function SceneRail() {
  const { t } = useTranslation('studio');
  const unit = useManuscriptUnit();
  const activeSceneId = useStudioBusSelector((s) => s.activeSceneId);

  if (!unit) return null;
  const scenes = unit.state.scenes;

  return (
    <div data-testid="studio-scene-rail" className="flex h-full w-56 flex-shrink-0 flex-col border-l">
      <div className="flex h-7 flex-shrink-0 items-center border-b px-2 text-[11px] font-medium text-muted-foreground">
        {t('sceneRail.title', { defaultValue: 'Scenes' })}
        <span className="ml-1 text-muted-foreground/60">{scenes.length}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {scenes.length === 0 ? (
          <p className="p-3 text-center text-[11px] text-muted-foreground">
            {t('sceneRail.empty', { defaultValue: 'No scenes for this chapter (outline it in the composer).' })}
          </p>
        ) : (
          scenes.map((s) => (
            <SceneRow key={s.id} scene={s} active={s.id === activeSceneId} onSaved={() => void unit.reloadScenes()} />
          ))
        )}
      </div>
    </div>
  );
}
