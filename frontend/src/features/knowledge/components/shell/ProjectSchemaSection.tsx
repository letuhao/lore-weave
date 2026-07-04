import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Skeleton } from '@/components/shared';
import {
  useGraphSchema,
  useGraphSchemaList,
  useSchemaAuthoring,
  useSchemaObserved,
  useSchemaUsageSummary,
} from '../../hooks/useGraphSchema';
import { SchemaWorkbench } from '../ontology/SchemaWorkbench';
import { CreateSchemaEntry } from '../ontology/CreateSchemaEntry';

// A3 — the FULL schema-authoring surface, on the KG PROJECT (the schema editor
// follows the KG, not the book). Resolves the project's ACTIVE project-scoped
// schema; if present → the redesigned full-CRUD SchemaWorkbench; if not → the
// create/clone/adopt entry so a human can DEFINE a schema from scratch.
export function ProjectSchemaSection({
  projectId,
  bookId,
  onAdoptCta,
}: {
  projectId: string;
  bookId: string | null;
  /** Threaded through to CreateSchemaEntry (DOCK-7 fix — see its own doc comment). */
  onAdoptCta?: () => void;
}) {
  const { t } = useTranslation('knowledge');
  const schemaList = useGraphSchemaList({ scope: 'all', project_id: projectId });
  const items = schemaList.data?.items ?? [];

  const activeSchemaId = useMemo(
    () =>
      items.find((s) => s.scope === 'project' && s.scope_id === projectId && !s.deprecated_at)?.schema_id ??
      null,
    [items, projectId],
  );
  // Clone SOURCES = every non-project (template) row the caller can see.
  const templates = useMemo(() => items.filter((s) => s.scope !== 'project'), [items]);

  const controller = useGraphSchema(activeSchemaId, projectId);
  const authoring = useSchemaAuthoring(projectId);
  const usage = useSchemaUsageSummary(activeSchemaId ? projectId : null).data;
  const observed = useSchemaObserved(activeSchemaId ? projectId : null).data;
  const busy = authoring.isCreating || authoring.isCloning;

  return (
    <div className="space-y-4" data-testid="project-schema-section">
      <p className="text-[12px] text-muted-foreground">{t('schemaSection.subtitle')}</p>

      {schemaList.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : activeSchemaId && controller.schema ? (
        <SchemaWorkbench
          controller={controller}
          usage={usage}
          observed={observed}
          projectId={projectId}
          getUsage={(nodeType, code) =>
            Promise.resolve({
              count: usage?.[nodeType as 'node_kind' | 'edge_type']?.[code] ?? 0,
              counted: nodeType === 'node_kind' || nodeType === 'edge_type',
            })
          }
        />
      ) : (
        <CreateSchemaEntry
          bookId={bookId}
          templates={templates}
          createBlank={authoring.createBlank}
          clone={authoring.clone}
          busy={busy}
          onAdoptCta={onAdoptCta}
        />
      )}
    </div>
  );
}
