import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { OntologyChip } from './OntologyChip';
import type { Cardinality, EdgeType, EdgeTypePatch } from '../../types/ontology';

// One edge-type row for the redesigned SchemaWorkbench: display + inline edit
// (attribute-only — `code` is IMMUTABLE, A1/EC-A6) + delete. Pure render; the
// PATCH/DELETE run through useGraphSchema via the callbacks.

interface Props {
  edge: EdgeType;
  disabled?: boolean;
  onPatch: (patch: EdgeTypePatch) => void;
  onDelete: () => void;
}

const csv = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean);

export function EdgeTypeRow({ edge, disabled, onPatch, onDelete }: Props) {
  const { t } = useTranslation('kgOntology');
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(edge.label);
  const [cardinality, setCardinality] = useState<Cardinality>(edge.cardinality);
  const [temporal, setTemporal] = useState(edge.temporal);
  const [src, setSrc] = useState((edge.source_node_kinds ?? []).join(', '));
  const [tgt, setTgt] = useState((edge.target_node_kinds ?? []).join(', '));
  const [description, setDescription] = useState(edge.description ?? '');

  const save = () => {
    onPatch({
      label: label.trim() || edge.label,
      cardinality,
      temporal,
      source_node_kinds: csv(src),
      target_node_kinds: csv(tgt),
      description,
    });
    setEditing(false);
  };

  if (editing) {
    return (
      <tr className="border-b last:border-0" data-testid={`edge-row-edit-${edge.code}`}>
        <td colSpan={4} className="py-2">
          <div className="grid gap-2 rounded-md border border-primary/40 bg-muted/20 p-2 text-[12px] sm:grid-cols-2">
            <label className="space-y-0.5">
              <span className="text-muted-foreground">{t('schema.label')}</span>
              <input value={label} onChange={(e) => setLabel(e.target.value)}
                className="w-full rounded-md border bg-background px-2 py-1"
                data-testid={`edge-edit-label-${edge.code}`} />
            </label>
            <label className="space-y-0.5">
              <span className="text-muted-foreground">{t('schema.cardinality')}</span>
              <select value={cardinality} onChange={(e) => setCardinality(e.target.value as Cardinality)}
                className="w-full rounded-md border bg-background px-2 py-1"
                data-testid={`edge-edit-cardinality-${edge.code}`}>
                <option value="single_active">single_active</option>
                <option value="multi_active">multi_active</option>
              </select>
            </label>
            <label className="space-y-0.5">
              <span className="text-muted-foreground">{t('schema.sourceKinds')}</span>
              <input value={src} onChange={(e) => setSrc(e.target.value)} placeholder="character, organization"
                className="w-full rounded-md border bg-background px-2 py-1" />
            </label>
            <label className="space-y-0.5">
              <span className="text-muted-foreground">{t('schema.targetKinds')}</span>
              <input value={tgt} onChange={(e) => setTgt(e.target.value)}
                className="w-full rounded-md border bg-background px-2 py-1" />
            </label>
            <label className="flex items-center gap-1.5 sm:col-span-2">
              <input type="checkbox" checked={temporal} onChange={(e) => setTemporal(e.target.checked)} />
              {t('schema.temporalField')}
            </label>
            <label className="space-y-0.5 sm:col-span-2">
              <span className="text-muted-foreground">{t('schema.descriptionField')}</span>
              <input value={description} onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-md border bg-background px-2 py-1" />
            </label>
            <div className="flex gap-2 sm:col-span-2">
              <button type="button" onClick={save} disabled={disabled}
                className="rounded-md bg-primary px-3 py-1 text-white disabled:opacity-50"
                data-testid={`edge-save-${edge.code}`}>{t('common.save')}</button>
              <button type="button" onClick={() => setEditing(false)}
                className="rounded-md border px-3 py-1">{t('common.cancel')}</button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b last:border-0" data-testid={`edge-row-${edge.code}`}>
      <td className="py-1.5">
        <OntologyChip variant="edge">{edge.code}</OntologyChip>
        {edge.deprecated_at && (
          <OntologyChip variant="deprecated" className="ml-1">{t('common.deprecated')}</OntologyChip>
        )}
      </td>
      <td className="py-1.5 text-muted-foreground">
        {(edge.source_node_kinds ?? []).join('/') || '—'} → {(edge.target_node_kinds ?? []).join('/') || '—'}
      </td>
      <td className="py-1.5">
        {edge.temporal && <OntologyChip variant="temporal">{t('schema.temporal')}</OntologyChip>}
        <span className="ml-1 text-[10px] text-muted-foreground">{edge.cardinality}</span>
      </td>
      <td className="py-1.5 text-right">
        {!edge.deprecated_at && (
          <span className="inline-flex gap-1">
            <button type="button" onClick={() => setEditing(true)} disabled={disabled}
              className="rounded border px-2 py-0.5 text-[11px]"
              data-testid={`edit-edge-${edge.code}`}>{t('common.edit')}</button>
            <button type="button" onClick={onDelete} disabled={disabled}
              className="rounded border px-2 py-0.5 text-[11px] text-rose-600"
              data-testid={`delete-edge-${edge.code}`}>{t('common.delete')}</button>
          </span>
        )}
      </td>
    </tr>
  );
}
