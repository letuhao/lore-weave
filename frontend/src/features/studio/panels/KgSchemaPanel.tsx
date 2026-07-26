import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { cn } from '@/lib/utils';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { useGraphSchema, useGraphSchemaList } from '@/features/knowledge/hooks/useGraphSchema';
import { useOntologyAdopt } from '@/features/knowledge/hooks/useOntologyAdopt';
import { useGraphViews } from '@/features/knowledge/hooks/useGraphViews';
import { useOntologySync } from '@/features/knowledge/hooks/useOntologySync';
import { AdoptPicker } from '@/features/knowledge/components/ontology/AdoptPicker';
import { ViewBuilder } from '@/features/knowledge/components/ontology/ViewBuilder';
import { SyncDiffPanel } from '@/features/knowledge/components/ontology/SyncDiffPanel';
import { ProjectSchemaSection } from '@/features/knowledge/components/shell/ProjectSchemaSection';
import { KgNoProjectState } from '@/features/knowledge/components/shell/KgNoProjectState';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

// 14_kg_panels.md K6 — the `kg-schema` studio panel: ONE panel bundling all four
// ontology capabilities (adopt/schema/views/sync), each of which used to be a
// tab inside the book-route `KnowledgeOntologyTab.tsx` (the `schema` tab of
// which had already been reduced to a <Navigate> redirect to the now-retired
// `ProjectDetailShell` route). Per K6 this stays ONE panel with its own
// internal tab furniture rather than 4 sibling dock panels — unlike Glossary's
// view-switch (DOCK-8 anti-pattern, fixed by splitting into sibling panels),
// these four views share ONE editing session over ONE active project schema;
// splitting them would fragment a single edit flow across 4 tabs with no
// independent use case (explicitly flagged as a DOCK-8 judgment-call exception
// in docs/standards/dockable-gui.md).
//
// Mirrors KnowledgeOntologyTab's `view` state + TABS array + adopt/views/sync
// render branches verbatim; the `schema` view now renders ProjectSchemaSection
// + SchemaWorkbench directly (this panel IS the schema-editing surface) instead
// of navigating away. Project resolution goes through useBookKnowledgeProject
// (K5) instead of an inline `projects.find(...)` lookup.
type OntologyView = 'adopt' | 'schema' | 'views' | 'sync';

export function KgSchemaPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-schema', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();
  const { bookId } = host;
  const { t } = useTranslation('kgOntology');

  const [view, setView] = useState<OntologyView>('adopt');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { projectId, isLoading: projectLoading } = useBookKnowledgeProject(bookId);

  // One schema list (system + user + this project); split client-side. Adopt
  // sources = the non-project (template) rows; the project's own active schema
  // drives the editor / views / sync. Hooks below are called unconditionally
  // (rules of hooks); they self-gate on projectId / selection via `enabled`.
  const schemaList = useGraphSchemaList({ scope: 'all', project_id: projectId ?? undefined });
  const allSchemas = schemaList.data?.items ?? [];
  const templates = useMemo(
    () => allSchemas.filter((s) => s.scope !== 'project' || s.scope_id === projectId),
    [allSchemas, projectId],
  );
  const activeSchemaId = useMemo(
    () =>
      allSchemas.find(
        (s) => s.scope === 'project' && s.scope_id === projectId && !s.deprecated_at,
      )?.schema_id ?? null,
    [allSchemas, projectId],
  );

  const schema = useGraphSchema(activeSchemaId, projectId);
  const adopt = useOntologyAdopt(projectId ?? '', selectedId);
  const views = useGraphViews(projectId ?? '');
  const sync = useOntologySync(projectId ?? '');

  const handleAdopt = async (schemaId: string) => {
    try {
      await adopt.adopt({ source_schema_id: schemaId });
      setSelectedId(null);
    } catch {
      // The M1 glossary gate (422) is surfaced as derived `needsGlossary` state
      // by the hook + rendered by AdoptPicker; the rejection never escapes.
    }
  };

  if (projectLoading) {
    return (
      <div className="h-full min-h-0 overflow-auto space-y-3 p-4" data-testid="studio-kg-schema-panel">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="h-full min-h-0 overflow-auto p-4" data-testid="studio-kg-schema-panel">
        <KgNoProjectState bookId={bookId} testId="kg-ontology-no-project" />
      </div>
    );
  }

  const edgeCodes = (schema.schema?.edge_types ?? []).map((e) => e.code);
  const nodeKindCodes = (schema.schema?.node_kinds ?? []).map((k) => k.kind_code);

  const TABS: { key: OntologyView; label: string }[] = [
    { key: 'adopt', label: t('page.tabs.adopt') },
    { key: 'schema', label: t('page.tabs.schema') },
    { key: 'views', label: t('page.tabs.views') },
    { key: 'sync', label: t('page.tabs.sync') },
  ];

  return (
    <div className="h-full min-h-0 overflow-auto space-y-4 p-4" data-testid="studio-kg-schema-panel">
      <div className="flex gap-1 rounded-lg border bg-card p-1">
        {TABS.map((tb) => (
          <button
            key={tb.key}
            type="button"
            onClick={() => setView(tb.key)}
            data-testid={`kg-schema-tab-${tb.key}`}
            className={cn(
              'rounded-md px-3 py-1.5 text-[12px] font-medium transition',
              view === tb.key
                ? 'bg-primary text-white'
                : 'text-muted-foreground hover:bg-muted/40',
            )}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {view === 'adopt' && (
        <AdoptPicker
          schemas={templates}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onAdopt={handleAdopt}
          isAdopting={adopt.isAdopting}
          needsGlossary={adopt.needsGlossary}
          // DOCK-7 — the classic tab navigated to /books/:bookId/glossary; a panel
          // opens the sibling `glossary` studio panel through the host instead.
          onOpenGlossary={() => host.openPanel('glossary')}
          onClearGate={adopt.clearGate}
          wouldLose={adopt.wouldLose}
          lossBlocked={adopt.lossBlocked}
          onAcknowledgeLoss={adopt.acknowledgeLoss}
        />
      )}

      {view === 'schema' && (
        <ProjectSchemaSection
          projectId={projectId}
          bookId={bookId}
          // DOCK-7 — CreateSchemaEntry's "Adopt a template" CTA switches this
          // panel's own internal tab instead of a hard route-link hop.
          onAdoptCta={() => setView('adopt')}
        />
      )}

      {view === 'views' && (
        <ViewBuilder
          availableEdgeTypes={edgeCodes}
          availableNodeKinds={nodeKindCodes}
          onSave={(body) => void views.createView(body)}
          isSaving={views.isMutating}
        />
      )}

      {view === 'sync' && (
        <SyncDiffPanel
          changes={sync.changes}
          hasUpdates={sync.hasUpdates}
          getChoice={sync.getChoice}
          onSetDecision={sync.setDecision}
          onKeepAllMine={sync.keepAllMine}
          onTakeAllTheirs={sync.takeAllTheirs}
          onApply={() => void sync.apply()}
          isApplying={sync.isApplying}
          decidedCount={sync.decidedCount}
        />
      )}
    </div>
  );
}
