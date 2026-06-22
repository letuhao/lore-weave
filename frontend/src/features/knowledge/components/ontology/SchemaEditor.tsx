import { useTranslation } from 'react-i18next';
import { OntologyChip } from './OntologyChip';
import type { GraphSchemaTree } from '../../types/ontology';

// Render-only schema editor (mirrors 02-schema-editor.html). Shows edge types,
// fact types, vocab sets/values, and expected node-kinds for one schema, each
// with a deprecate action (deprecate-only, M3). Add actions are delegated to
// child forms passed via render props. Logic lives in useGraphSchema.

interface Props {
  schema: GraphSchemaTree;
  onDeprecateEdgeType: (code: string) => void;
  readOnly?: boolean;
}

export function SchemaEditor({ schema, onDeprecateEdgeType, readOnly }: Props) {
  const { t } = useTranslation('kgOntology');
  return (
    <div className="space-y-5" data-testid="schema-editor">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold">{schema.name}</h2>
          <p className="text-[11px] text-muted-foreground">
            <OntologyChip variant="project">
              {schema.scope} · v{schema.schema_version}
            </OntologyChip>
          </p>
        </div>
      </header>

      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">
          {t('schema.edgeTypes')}
        </h3>
        <table className="w-full text-left text-[12px]">
          <tbody>
            {(schema.edge_types ?? []).map((e) => (
              <tr key={e.code} className="border-b last:border-0">
                <td className="py-1.5">
                  <OntologyChip variant="edge">{e.code}</OntologyChip>
                  {e.deprecated_at && (
                    <OntologyChip variant="deprecated" className="ml-1">
                      {t('common.deprecated')}
                    </OntologyChip>
                  )}
                </td>
                <td className="py-1.5 text-muted-foreground">
                  {(e.source_node_kinds ?? []).join('/') || '—'} →{' '}
                  {(e.target_node_kinds ?? []).join('/') || '—'}
                </td>
                <td className="py-1.5">
                  {e.temporal && (
                    <OntologyChip variant="temporal">{t('schema.temporal')}</OntologyChip>
                  )}
                </td>
                <td className="py-1.5 text-right">
                  {!readOnly && !e.deprecated_at && (
                    <button
                      type="button"
                      onClick={() => onDeprecateEdgeType(e.code)}
                      className="rounded border px-2 py-0.5 text-[11px] text-rose-600"
                      data-testid={`deprecate-edge-${e.code}`}
                    >
                      {t('common.deprecate')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(schema.edge_types ?? []).length === 0 && (
              <tr>
                <td className="py-1.5 text-muted-foreground">{t('schema.noEdges')}</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">
            {t('schema.factTypes')}
          </h3>
          <ul className="flex flex-wrap gap-1">
            {(schema.fact_types ?? []).map((f) => (
              <li key={f.code}>
                <OntologyChip variant="neutral">{f.label}</OntologyChip>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">
            {t('schema.nodeKinds')}
          </h3>
          <ul className="flex flex-wrap gap-1">
            {(schema.node_kinds ?? []).map((k) => (
              <li key={k.kind_code}>
                <OntologyChip variant="glossary">
                  {k.kind_code} · {k.strength}
                </OntologyChip>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {(schema.vocab_sets ?? []).map((vs) => (
        <section key={vs.code}>
          <h3 className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">
            {t('schema.vocabSet')} · {vs.label}{' '}
            {vs.closed && (
              <span className="font-normal lowercase text-muted-foreground">
                ({t('schema.closed')})
              </span>
            )}
          </h3>
          <ul className="flex flex-wrap gap-1">
            {(vs.values ?? []).map((v) => (
              <li key={v.code}>
                <OntologyChip variant="drive">{v.code}</OntologyChip>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
