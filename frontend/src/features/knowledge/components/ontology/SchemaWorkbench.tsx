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
import { InferFromGraphPanel, type InferEdgePick } from './InferFromGraphPanel';
import type { ObservedComponents } from '../../types/ontology';
import type { useGraphSchema } from '../../hooks/useGraphSchema';

type SchemaController = ReturnType<typeof useGraphSchema>;

// Redesigned full-CRUD authoring surface (A1/A3). A card-per-section layout —
// header (editable name + scope/version + allow_free_edges) then Edge types /
// Node kinds / Fact types / Vocab sets, each with inline edit + delete + add.
// All logic lives in useGraphSchema; this renders + wires the callbacks. `code`
// is never editable (immutable — a rename = delete + re-create).
interface UsageResult {
  count: number;
  counted: boolean;
}

export function SchemaWorkbench({
  controller,
  getUsage,
  usage,
  observed,
}: {
  controller: SchemaController;
  // A4 — resolve how many graph elements reference a component before deleting it.
  // Omitted (e.g. in tests / user-tier templates with no graph) → delete directly.
  getUsage?: (nodeType: string, code: string) => Promise<UsageResult>;
  // M1 — preloaded usage counts for inline "· used by N" badges.
  usage?: { node_kind: Record<string, number>; edge_type: Record<string, number> };
  // M3a — what the extracted graph already contains (promote-to-schema panel).
  observed?: ObservedComponents;
}) {
  const { t } = useTranslation('kgOntology');
  const [editingName, setEditingName] = useState(false);
  const [name, setName] = useState('');
  const [newSetCode, setNewSetCode] = useState('');
  const [newSetLabel, setNewSetLabel] = useState('');
  const [pending, setPending] = useState<
    { nodeType: string; code: string; count: number; run: () => void } | null
  >(null);
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

  // A4 — before deleting, check how many graph elements still reference the
  // component; only ask to confirm when count > 0. A failed/absent check never
  // blocks the delete (project DELETE only soft-deprecates — data stays safe).
  const requestDelete = async (nodeType: string, code: string, run: () => void) => {
    if (!getUsage) return run();
    try {
      const { count } = await getUsage(nodeType, code);
      if (count > 0) setPending({ nodeType, code, count, run });
      else run();
    } catch {
      run();
    }
  };

  const busy = controller.isMutating;
  const kindCodes = (schema.node_kinds ?? []).map((k) => k.kind_code);
  const edgeCodes = (schema.edge_types ?? []).map((e) => e.code);

  // M3a — promote observed graph components: add kinds FIRST (so an edge's
  // source/target kinds exist), then edges. One toast for the batch.
  const inferAdd = async (kinds: string[], edges: InferEdgePick[]) => {
    try {
      for (const kc of kinds) await controller.addNodeKind({ kind_code: kc, strength: 'optional' });
      for (const e of edges)
        await controller.addEdgeType({
          code: e.code, label: e.code,
          source_node_kinds: e.source_kinds, target_node_kinds: e.target_kinds,
        });
      toast.success(t('infer.added', { count: kinds.length + edges.length }));
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('schema.forbidden') : (e as Error).message;
      toast.error(msg || t('schema.addFailed'));
    }
  };

  return (
    <div className="space-y-4" data-testid="schema-workbench">
      {/* header */}
      <header className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
        {editingName ? (
          <>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus
              className="rounded-md border bg-input px-2 py-1 text-sm"
              data-testid="schema-name-input" />
            <button type="button" disabled={busy} data-testid="save-schema-name"
              onClick={() => { void guard(() => controller.patchMeta({ name: name.trim() || schema.name })); setEditingName(false); }}
              className="rounded-md bg-primary px-2.5 py-1 text-[12px] text-primary-foreground">{t('common.save')}</button>
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

      {/* M3a — promote what the extracted graph already contains */}
      {observed && (
        <InferFromGraphPanel
          observed={observed}
          existingKinds={new Set(kindCodes)}
          existingEdges={new Set(edgeCodes)}
          disabled={busy}
          onAdd={(kinds, edges) => void inferAdd(kinds, edges)}
        />
      )}

      {/* empty-state coaching (M1) — a brand-new blank schema */}
      {kindCodes.length === 0 && (schema.edge_types ?? []).length === 0 && (
        <div className="rounded-lg border border-dashed p-4 text-center" data-testid="schema-empty-coach">
          <p className="text-sm font-medium">{t('schema.emptyTitle')}</p>
          <p className="mt-1 text-[12px] text-muted-foreground">{t('schema.emptyHelp')}</p>
        </div>
      )}

      {/* edge types */}
      <section className="rounded-lg border p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">{t('schema.edgeTypes')}</h3>
        <table className="w-full text-left text-[12px]">
          <tbody>
            {(schema.edge_types ?? []).map((e) => (
              <EdgeTypeRow key={e.code} edge={e} disabled={busy} usageCount={usage?.edge_type[e.code]}
                availableKinds={kindCodes}
                onPatch={(patch) => void guard(() => controller.patchEdgeType({ code: e.code, patch }))}
                onDelete={() => void requestDelete('edge_type', e.code,
                  () => void guard(() => controller.deleteEdgeType(e.code), t('common.deleted')))} />
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
              <NodeKindRow key={k.kind_code} nodeKind={k} disabled={busy} usageCount={usage?.node_kind[k.kind_code]}
                onPatchStrength={(strength) => void guard(() => controller.patchNodeKind({ code: k.kind_code, patch: { strength } }))}
                onDelete={() => void requestDelete('node_kind', k.kind_code,
                  () => void guard(() => controller.deleteNodeKind(k.kind_code), t('common.deleted')))} />
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
                onDelete={() => void requestDelete('fact_type', f.code,
                  () => void guard(() => controller.deleteFactType(f.code), t('common.deleted')))} />
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
            onDeleteSet={() => void requestDelete('vocab_set', vs.code,
              () => void guard(() => controller.deleteVocabSet(vs.code), t('common.deleted')))}
            onAddValue={(body) => void guard(() => controller.addVocabValue({ setCode: vs.code, body }))}
            onPatchValue={(code, patch) => void guard(() => controller.patchVocabValue({ setCode: vs.code, code, patch }))}
            onDeleteValue={(code) => void requestDelete('vocab_value', code,
              () => void guard(() => controller.deleteVocabValue({ setCode: vs.code, code }), t('common.deleted')))} />
        ))}
        <div className="flex flex-wrap items-center gap-1.5 border-t pt-2">
          <input value={newSetCode} onChange={(e) => setNewSetCode(e.target.value)} placeholder={t('schema.code')}
            className="w-28 rounded-md border bg-input px-2 py-1 text-[11px]" data-testid="new-vocab-set-code" />
          <input value={newSetLabel} onChange={(e) => setNewSetLabel(e.target.value)} placeholder={t('schema.label')}
            className="w-32 rounded-md border bg-input px-2 py-1 text-[11px]" data-testid="new-vocab-set-label" />
          <button type="button" disabled={busy || !newSetCode.trim() || !newSetLabel.trim()}
            onClick={() => { void guard(() => controller.addVocabSet({ code: newSetCode.trim(), label: newSetLabel.trim() })); setNewSetCode(''); setNewSetLabel(''); }}
            className="rounded-md border px-2 py-1 text-[11px] disabled:opacity-50"
            data-testid="add-vocab-set">{t('schema.addVocabSet')}</button>
        </div>
      </section>

      {/* A4 — orphan-count delete confirm (only when graph elements reference it) */}
      {pending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog" aria-modal="true" data-testid="delete-confirm">
          <div className="w-full max-w-md space-y-3 rounded-lg border bg-card p-4 shadow-lg">
            <h3 className="text-sm font-bold">{t('schema.deleteConfirmTitle')}</h3>
            <p className="text-[12px] text-muted-foreground" data-testid="delete-confirm-message">
              {t('schema.deleteConfirmBody', { code: pending.code, count: pending.count })}
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setPending(null)}
                className="rounded-md border px-3 py-1.5 text-[12px]"
                data-testid="delete-confirm-cancel">{t('common.cancel')}</button>
              <button type="button"
                onClick={() => { pending.run(); setPending(null); }}
                className="rounded-md bg-rose-600 px-3 py-1.5 text-[12px] font-medium text-white"
                data-testid="delete-confirm-yes">{t('common.delete')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
