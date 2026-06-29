import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Pencil } from 'lucide-react';
import { Skeleton } from '@/components/shared';
import { useResolvedSchema } from '../../hooks/useResolvedSchema';
import { SchemaEditor } from '../ontology/SchemaEditor';
import type { GraphSchemaTree } from '../../types/ontology';

// #28 (Part A) — read-only Schema inspector for the standalone Knowledge GUI.
// Resolves the project's EFFECTIVE schema (system→user→project merge) and renders
// it through SchemaEditor in readOnly mode (zero new render code). An "Edit schema"
// CTA deep-links to the book's ontology Schema tab (the authoring surface, Part B).
export function ProjectSchemaSection({
  projectId,
  bookId,
}: {
  projectId: string;
  bookId: string | null;
}) {
  const { t } = useTranslation('knowledge');
  const { schema, isLoading, isError } = useResolvedSchema(projectId);

  // Adapt the resolved schema (no name/scope) into the tree shape SchemaEditor reads.
  const tree = useMemo<GraphSchemaTree | null>(
    () =>
      schema
        ? {
            schema_id: `resolved:${projectId}`,
            scope: 'project',
            scope_id: projectId,
            code: 'resolved',
            name: t('schemaSection.title'),
            schema_version: schema.schema_version,
            allow_free_edges: schema.allow_free_edges,
            edge_types: schema.edge_types,
            fact_types: schema.fact_types,
            vocab_sets: schema.vocab_sets,
            node_kinds: schema.node_kinds,
          }
        : null,
    [schema, projectId, t],
  );

  return (
    <div className="space-y-4" data-testid="project-schema-section">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12px] text-muted-foreground">{t('schemaSection.subtitle')}</p>
        {bookId && (
          <Link
            to={`/books/${bookId}/kg-ontology?view=schema`}
            className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
            data-testid="schema-edit-cta"
          >
            <Pencil className="h-3.5 w-3.5" />
            {t('schemaSection.editCta')}
          </Link>
        )}
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError || !tree ? (
        <p className="rounded-lg border p-6 text-center text-[12px] text-muted-foreground" data-testid="schema-section-empty">
          {t('schemaSection.error')}
        </p>
      ) : (
        <div className="rounded-lg border p-4">
          <p className="mb-3 text-[11px] text-muted-foreground">
            {tree.allow_free_edges ? t('schemaSection.freeEdges') : t('schemaSection.closedEdges')}
          </p>
          <SchemaEditor schema={tree} onDeprecateEdgeType={() => {}} readOnly />
        </div>
      )}
    </div>
  );
}
