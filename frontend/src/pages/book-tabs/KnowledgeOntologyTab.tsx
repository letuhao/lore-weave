import { useMemo, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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

// C3 wiring (D-KG-ONTOLOGY-FE-WIRING) — mounts the KG customizable-ontology
// surfaces (adopt / schema / views / sync) as a book tab. Resolves the book's
// knowledge project (book_id FK), then drives the lane-LE/LC/LD components off
// their hooks. The component only wires + renders; all logic lives in the hooks.

type OntologyView = 'adopt' | 'schema' | 'views' | 'sync';

export function KnowledgeOntologyTab({ bookId }: { bookId: string }) {
  const { t } = useTranslation('kgOntology');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Honor a ?view=<tab> deep-link (e.g. the Knowledge-GUI "Edit schema" CTA →
  // ?view=schema lands the user straight on the schema authoring surface).
  const initialView = useMemo<OntologyView>(() => {
    const v = searchParams.get('view');
    return v === 'schema' || v === 'views' || v === 'sync' ? v : 'adopt';
    // intentionally seed once from the initial URL; tab clicks own it after.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [view, setView] = useState<OntologyView>(initialView);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { projectId, isLoading: projectsLoading } = useBookKnowledgeProject(bookId);

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

  if (projectsLoading) {
    return (
      <div className="space-y-3 p-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!projectId) {
    return (
      <div
        className="rounded-lg border p-8 text-center"
        data-testid="kg-ontology-no-project"
      >
        <p className="text-sm font-medium">{t('page.noProject')}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t('page.noProjectHelp')}</p>
      </div>
    );
  }

  // A3 — schema authoring now lives with the KG PROJECT (the schema editor
  // follows the KG, not the book). The "Schema" tab (or a stale ?view=schema
  // deep-link) redirects to the project surface instead of mounting the editor here.
  if (view === 'schema') {
    return <Navigate to={`/knowledge/projects/${projectId}/schema`} replace />;
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
    <div className="space-y-4" data-testid="kg-ontology-tab">
      <div className="flex gap-1 rounded-lg border bg-card p-1">
        {TABS.map((tb) => (
          <button
            key={tb.key}
            type="button"
            onClick={() => setView(tb.key)}
            data-testid={`kg-ontology-tab-${tb.key}`}
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
          onOpenGlossary={(bid) => navigate(`/books/${bid ?? bookId}/glossary`)}
          onClearGate={adopt.clearGate}
          wouldLose={adopt.wouldLose}
          lossBlocked={adopt.lossBlocked}
          onAcknowledgeLoss={adopt.acknowledgeLoss}
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
