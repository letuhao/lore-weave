import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { SchemaEditor } from './SchemaEditor';
import { AddEdgeTypeForm } from './AddEdgeTypeForm';
import { AddNodeKindForm } from './AddNodeKindForm';
import { AddFactTypeForm } from './AddFactTypeForm';
import { AddVocabValueForm } from './AddVocabValueForm';
import type { useGraphSchema } from '../../hooks/useGraphSchema';

type SchemaController = ReturnType<typeof useGraphSchema>;

// #28 Part B — the human schema-authoring surface for the book GUI. Composes the
// read view (SchemaEditor + deprecate-edge) with the additive add-forms + the
// allow_free_edges toggle, all on the already-wired useGraphSchema mutations.
// The schema model is additive + deprecate-edge-only (mirrors the AI's edits).
export function SchemaWorkbench({ controller }: { controller: SchemaController }) {
  const { t } = useTranslation('kgOntology');
  const schema = controller.schema;
  if (!schema) return null;

  // Surface a mutation outcome as a toast (mirrors the glossary Manage guard);
  // a 403 (no Manage on the project) gets a clear message, else the error text.
  const guard = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      toast.success(t('schema.added'));
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('schema.forbidden') : (e as Error).message;
      toast.error(msg || t('schema.addFailed'));
    }
  };

  return (
    <div className="space-y-5" data-testid="schema-workbench">
      <SchemaEditor
        schema={schema}
        onDeprecateEdgeType={(code) =>
          void guard(() => controller.deprecateEdgeType(code))
        }
      />

      <section className="space-y-3 border-t pt-4">
        <div>
          <h3 className="text-sm font-bold">{t('schema.addSectionTitle')}</h3>
          <p className="text-[11px] text-muted-foreground">{t('schema.editHint')}</p>
        </div>

        <label className="flex items-center gap-2 text-[12px]">
          <input
            type="checkbox"
            checked={schema.allow_free_edges}
            disabled={controller.isMutating}
            onChange={(e) => void guard(() => controller.patchMeta({ allow_free_edges: e.target.checked }))}
            data-testid="allow-free-edges-toggle"
          />
          {t('schema.allowFreeEdges')}
        </label>

        <div className="grid gap-3 lg:grid-cols-2">
          <AddEdgeTypeForm
            isSubmitting={controller.isMutating}
            onSubmit={(b) => void guard(() => controller.addEdgeType(b))}
          />
          <AddNodeKindForm
            isSubmitting={controller.isMutating}
            onSubmit={(b) => void guard(() => controller.addNodeKind(b))}
          />
          <AddFactTypeForm
            isSubmitting={controller.isMutating}
            onSubmit={(b) => void guard(() => controller.addFactType(b))}
          />
          <AddVocabValueForm
            vocabSets={schema.vocab_sets ?? []}
            isSubmitting={controller.isMutating}
            onSubmit={(a) => void guard(() => controller.addVocabValue(a))}
          />
        </div>
      </section>
    </div>
  );
}
