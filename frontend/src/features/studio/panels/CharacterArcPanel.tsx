// s7-4 — `character-arc` dock panel: a thin leaf-reuse wrapper around the
// existing composition <CharacterArcView>. Resolves its subject via the
// arc-inspector AI-1 three-tier precedence (DP-5):
//   1. props.params.entityId — an in-studio deep-link (the cast-row launcher).
//   2. bus.activeCastEntityId — an additive bus slice (DEFERRED to the
//      integrator manifest; see the RETURN block) so cast↔arc stay in sync.
//   3. the in-panel picker — CharacterArcView already has one (never a dead
//      panel on a bare-id open).
// The spoiler window is the BUS chapter (DP-2 — no second picker here). The
// ENHANCE toolbar reuses EntityEditDialog (edit) + CreateRelationDialog (+ link)
// over the existing routes.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { Pencil, Link2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { CharacterArcView } from '@/features/composition/components/CharacterArcView';
import { EntityEditDialog } from '@/features/knowledge/components/EntityEditDialog';
import { CreateRelationDialog } from '@/features/knowledge/components/CreateRelationDialog';
import { useEntityDetail } from '@/features/knowledge/hooks/useEntityDetail';
import { useStudioHost, useStudioBusSelector } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function CharacterArcPanel(props: IDockviewPanelProps) {
  useStudioPanel('character-arc', props.api, { mcpToolPrefixes: ['kg_'] });
  const { t } = useTranslation('composition');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const activeChapterId = useStudioBusSelector((s) => s.activeChapterId);

  // Tier 1 (deep-link param) seeds the controlled subject; the in-panel picker
  // (tier 3) then owns it. Tier 2 (bus.activeCastEntityId) lands via the manifest
  // bus-slice the integrator adds — decompose, don't block the core port on it.
  const paramEntityId =
    (props.params as { entityId?: string } | undefined)?.entityId ?? null;
  const [entityId, setEntityId] = useState<string | null>(paramEntityId);

  const { detail } = useEntityDetail(entityId);
  const entity = detail?.entity ?? null;

  const [editOpen, setEditOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['composition', 'arc'] });
    void queryClient.invalidateQueries({ queryKey: ['composition', 'cast'] });
  };

  return (
    <div data-testid="studio-character-arc-panel" className="flex h-full min-h-0 flex-col">
      {entity && (
        <div className="flex flex-shrink-0 items-center gap-2 border-b px-3 py-1 text-[11px]">
          <button
            type="button"
            data-testid="arc-edit-entity"
            className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 hover:bg-accent/50"
            onClick={() => setEditOpen(true)}
          >
            <Pencil className="h-3 w-3" />
            {t('chararc.edit', { defaultValue: 'Edit' })}
          </button>
          {entity.project_id && (
            <button
              type="button"
              data-testid="arc-link-entity"
              className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 hover:bg-accent/50"
              onClick={() => setLinkOpen(true)}
            >
              <Link2 className="h-3 w-3" />
              {t('chararc.linkEntity', { defaultValue: '+ link entity' })}
            </button>
          )}
        </div>
      )}

      <div className="min-h-0 flex-1">
        <CharacterArcView
          bookId={host.bookId}
          chapterId={activeChapterId ?? ''}
          token={accessToken}
          entityId={entityId}
          onEntityChange={setEntityId}
        />
      </div>

      {entity && (
        <EntityEditDialog
          open={editOpen}
          onOpenChange={(o) => {
            setEditOpen(o);
            if (!o) refresh();
          }}
          entity={entity}
        />
      )}
      {entity?.project_id && (
        <CreateRelationDialog
          open={linkOpen}
          onOpenChange={setLinkOpen}
          projectId={entity.project_id}
          subjectId={entity.id}
          subjectName={entity.name}
        />
      )}
    </div>
  );
}
