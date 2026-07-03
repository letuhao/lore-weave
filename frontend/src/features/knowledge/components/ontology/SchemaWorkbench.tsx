import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { OntologyChip } from './OntologyChip';
import { EdgeTypeRow } from './EdgeTypeRow';
import { NodeKindRow } from './NodeKindRow';
import { FactTypeRow } from './FactTypeRow';
import { VocabSetCard } from './VocabSetCard';
import { AddEdgeTypeForm } from './AddEdgeTypeForm';
import { AddNodeKindForm } from './AddNodeKindForm';
import { AddFactTypeForm } from './AddFactTypeForm';
import type { useGraphSchema } from '../../hooks/useGraphSchema';

type SchemaController = ReturnType<typeof useGraphSchema>;

// Redesigned full-CRUD authoring surface (A1/A3). A card-per-section layout —
// header (editable name + scope/version + allow_free_edges) then Edge types /
// Node kinds / Fact types / Vocab sets, each with inline edit + delete + add.
// All logic lives in useGraphSchema; this renders + wires the callbacks. `code`
// is never editable (immutable — a rename = delete + re-create).
export function SchemaWorkbench({ controller }: { controller: SchemaController }) {
  const { t } = useTranslation('kgOntology');
  const [editingName, setEditingName] = useState(false);
  const [name, setName] = useState('');
  const [newSetCode, setNewSetCode] = useState('');
  const [newSetLabel, setNewSetLabel] = useState('');
  const schema = controller.schema;
  if (!schema) return null;

  // Surface a mutation outcome as a toast; a 403 (no Manage on the project) gets
  // a clear message, else the server error text (self-correcting for the user).
  const guard = async (fn: () => Promise<unknown>, ok = t('schema.saved')) => {
    try {
      await fn();
      toast.success(ok);
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('schema.forbidden') : (e as Error).message;
      toast.error(msg || t('schema.addFailed'));
    }
  };

  const busy = controller.isMutating;

  return (
    <div className="space-y-4" data-testid="schema-workbench">
      {/* header */}
      <header className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
        {editingName ? (
          <>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus
              className="rounded-md border bg-background px-2 py-1 text-sm"
              data-testid="schema-name-input" />
            <button type="button" disabled={busy} data-testid="save-schema-name"
              onClick={() => { void guard(() => controller.patchMeta({ name: name.trim() || schema.name })); setEditingName(false); }}
              className="rounded-md bg-primary px-2.5 py-1 text-[12px] text-white">{t('common.save')}</button>
            <button type="button" onClick={() => setEditingName(false)}
              className="rounded-md border px-2.5 py-1 text-[12px]">{t('common.cancel')}</button>
          </>
        ) : (
          <>
            <h2 className="text-sm font-bold">{schema.name}</h2>
            <OntologyChip variant="project">{schema.scope} · v{schema.schema_version}</OntologyChip>
            <button type="button" onClick={() => { setName(schema.name); setEditingName(true); }}
              className="rounded border px-2 py-0.5 text-[11px]"
              data-testid="edit-schema-name">{t('common.edit')}</button>
          </>
        )}
        <label className="ml-auto flex items-center gap-2 text-[12px]">
          <input type="checkbox" checked={schema.allow_free_edges} disabled={busy}
            onChange={(e) => void guard(() => controller.patchMeta({ allow_free_edges: e.target.checked }))}
            data-testid="allow-free-edges-toggle" />
          {t('schema.allowFreeEdges')}
        </label>
      </header>

      {/* edge types */}
      <section className="rounded-lg border p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">{t('schema.edgeTypes')}</h3>
        <table className="w-full text-left text-[12px]">
          <tbody>
            {(schema.edge_types ?? []).map((e) => (
              <EdgeTypeRow key={e.code} edge={e} disabled={busy}
                onPatch={(patch) => void guard(() => controller.patchEdgeType({ code: e.code, patch }))}
                onDelete={() => void guard(() => controller.deleteEdgeType(e.code), t('common.deleted'))} />
            ))}
            {(schema.edge_types ?? []).length === 0 && (
              <tr><td className="py-1.5 text-muted-foreground">{t('schema.noEdges')}</td></tr>
            )}
          </tbody>
        </table>
        <div className="mt-3">
          <AddEdgeTypeForm isSubmitting={busy} onSubmit={(b) => void guard(() => controller.addEdgeType(b))} />
        </div>
      </section>

      {/* node kinds + fact types */}
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">{t('schema.nodeKinds')}</h3>
          <ul>
            {(schema.node_kinds ?? []).map((k) => (
              <NodeKindRow key={k.kind_code} nodeKind={k} disabled={busy}
                onPatchStrength={(strength) => void guard(() => controller.patchNodeKind({ code: k.kind_code, patch: { strength } }))}
                onDelete={() => void guard(() => controller.deleteNodeKind(k.kind_code), t('common.deleted'))} />
            ))}
          </ul>
          <div className="mt-3">
            <AddNodeKindForm isSubmitting={busy} onSubmit={(b) => void guard(() => controller.addNodeKind(b))} />
          </div>
        </section>

        <section className="rounded-lg border p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">{t('schema.factTypes')}</h3>
          <ul>
            {(schema.fact_types ?? []).map((f) => (
              <FactTypeRow key={f.code} factType={f} disabled={busy}
                onPatch={(patch) => void guard(() => controller.patchFactType({ code: f.code, patch }))}
                onDelete={() => void guard(() => controller.deleteFactType(f.code), t('common.deleted'))} />
            ))}
          </ul>
          <div className="mt-3">
            <AddFactTypeForm isSubmitting={busy} onSubmit={(b) => void guard(() => controller.addFactType(b))} />
          </div>
        </section>
      </div>

      {/* vocab sets */}
      <section className="space-y-3 rounded-lg border p-3">
        <h3 className="text-[11px] font-semibold uppercase text-muted-foreground">{t('schema.vocabSets')}</h3>
        {(schema.vocab_sets ?? []).map((vs) => (
          <VocabSetCard key={vs.code} set={vs} disabled={busy}
            onPatchSet={(patch) => void guard(() => controller.patchVocabSet({ setCode: vs.code, patch }))}
            onDeleteSet={() => void guard(() => controller.deleteVocabSet(vs.code), t('common.deleted'))}
            onAddValue={(body) => void guard(() => controller.addVocabValue({ setCode: vs.code, body }))}
            onPatchValue={(code, patch) => void guard(() => controller.patchVocabValue({ setCode: vs.code, code, patch }))}
            onDeleteValue={(code) => void guard(() => controller.deleteVocabValue({ setCode: vs.code, code }), t('common.deleted'))} />
        ))}
        <div className="flex flex-wrap items-center gap-1.5 border-t pt-2">
          <input value={newSetCode} onChange={(e) => setNewSetCode(e.target.value)} placeholder={t('schema.code')}
            className="w-28 rounded-md border bg-background px-2 py-1 text-[11px]" data-testid="new-vocab-set-code" />
          <input value={newSetLabel} onChange={(e) => setNewSetLabel(e.target.value)} placeholder={t('schema.label')}
            className="w-32 rounded-md border bg-background px-2 py-1 text-[11px]" data-testid="new-vocab-set-label" />
          <button type="button" disabled={busy || !newSetCode.trim() || !newSetLabel.trim()}
            onClick={() => { void guard(() => controller.addVocabSet({ code: newSetCode.trim(), label: newSetLabel.trim() })); setNewSetCode(''); setNewSetLabel(''); }}
            className="rounded-md border px-2 py-1 text-[11px] disabled:opacity-50"
            data-testid="add-vocab-set">{t('schema.addVocabSet')}</button>
        </div>
      </section>
    </div>
  );
}
