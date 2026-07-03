import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { Skeleton } from '@/components/shared';
import { useGraphSchema, useGraphSchemaList, useSchemaAuthoring } from '../../hooks/useGraphSchema';
import { ontologyApi } from '../../api/ontology';
import { SchemaWorkbench } from '../ontology/SchemaWorkbench';
import { CreateSchemaEntry } from '../ontology/CreateSchemaEntry';

// A3 — the FULL schema-authoring surface, on the KG PROJECT (the schema editor
// follows the KG, not the book). Resolves the project's ACTIVE project-scoped
// schema; if present → the redesigned full-CRUD SchemaWorkbench; if not → the
// create/clone/adopt entry so a human can DEFINE a schema from scratch.
export function ProjectSchemaSection({
  projectId,
  bookId,
}: {
  projectId: string;
  bookId: string | null;
}) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
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
  const busy = authoring.isCreating || authoring.isCloning;

  return (
    <div className="space-y-4" data-testid="project-schema-section">
      <p className="text-[12px] text-muted-foreground">{t('schemaSection.subtitle')}</p>

      {schemaList.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : activeSchemaId && controller.schema ? (
        <SchemaWorkbench
          controller={controller}
          getUsage={(nodeType, code) =>
            ontologyApi.schemaComponentUsage(projectId, nodeType, code, accessToken!)
          }
        />
      ) : (
        <CreateSchemaEntry
          bookId={bookId}
          templates={templates}
          createBlank={authoring.createBlank}
          clone={authoring.clone}
          busy={busy}
        />
      )}
    </div>
  );
}
