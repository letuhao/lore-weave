// s7-4 — `cast` dock panel: a thin leaf-reuse wrapper around the existing
// composition <CastCodexPanel>. Supplies bookId + the spoiler window from the
// BUS (bus.activeChapterId, NOT a page prop — DP-2: no second chapter picker),
// the arc deep-link (onViewArc → openPanel('character-arc',{params:{entityId}})),
// and the ADDITIVE edit layer (inline rename / edit dialog / archive / + New) via
// the useCastEdit OCC controller. The leaf renders; this wrapper owns wiring.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { CastCodexPanel } from '@/features/composition/components/CastCodexPanel';
import { useKnowledgeProjectId, type CastRow } from '@/features/composition/hooks/useCast';
import { useCastEdit } from '@/features/composition/hooks/useCastEdit';
import { EntityEditDialog } from '@/features/knowledge/components/EntityEditDialog';
import { CreateEntityDialog } from '@/features/knowledge/components/CreateEntityDialog';
import { useStudioHost, useStudioBusSelector } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function CastPanel(props: IDockviewPanelProps) {
  useStudioPanel('cast', props.api, { mcpToolPrefixes: ['kg_'] });
  const { t } = useTranslation('composition');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const activeChapterId = useStudioBusSelector((s) => s.activeChapterId);
  const projectQ = useKnowledgeProjectId(host.bookId, accessToken);
  const projectId = projectQ.data ?? null;

  const [editRow, setEditRow] = useState<CastRow | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const edit = useCastEdit({
    onRenameConflict: () => toast.error(t('codex.renameConflict', { defaultValue: 'Changed elsewhere — reloaded.' })),
    onArchived: () => toast.success(t('codex.archived', { defaultValue: 'Retired — it returns if the book mentions it again.' })),
    onError: (err) => toast.error(t('codex.editFailed', { defaultValue: 'Edit failed: {{error}}', error: err.message })),
  });

  const refreshCodex = () => {
    void queryClient.invalidateQueries({ queryKey: ['composition', 'cast'] });
    void queryClient.invalidateQueries({ queryKey: ['composition', 'arc'] });
  };

  const handleArchive = (row: CastRow) => {
    if (!window.confirm(t('codex.archiveConfirm', {
      defaultValue: 'Retire “{{name}}”? Its relations and glossary anchor are kept; it returns if the book mentions it again (there is no restore button).',
      name: row.name,
    }))) return;
    void edit.archive({ entityId: row.id });
  };

  return (
    <div data-testid="studio-cast-panel" className="flex h-full min-h-0 flex-col">
      <CastCodexPanel
        bookId={host.bookId}
        chapterId={activeChapterId ?? ''}
        token={accessToken}
        onViewArc={(entityId) => {
          // Tier-1 deep-link (params) opens/focuses the panel with this subject;
          // tier-2 bus event re-subjects an ALREADY-OPEN arc panel (S7
          // D-CAST-ARC-BUS-SLICE) so clicking a different cast row switches it.
          host.publish({ type: 'castEntity', entityId });
          host.openPanel('character-arc', { params: { entityId }, focus: true });
        }}
        onRename={(args) => void edit.rename(args)}
        onEdit={(row) => setEditRow(row)}
        onArchive={handleArchive}
        onNewEntity={projectId ? () => setCreateOpen(true) : undefined}
      />

      {editRow && (
        <EntityEditDialog
          open={editRow !== null}
          onOpenChange={(o) => {
            if (!o) {
              setEditRow(null);
              // EntityEditDialog invalidates only the knowledge-* keys; the codex
              // reads the composition namespace, so refresh it on close (a
              // redundant refetch on cancel is a harmless idempotent read).
              refreshCodex();
            }
          }}
          entity={editRow}
        />
      )}

      {projectId && (
        <CreateEntityDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          projectId={projectId}
        />
      )}
    </div>
  );
}
