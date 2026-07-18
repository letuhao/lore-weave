// PlanForge S3 (D-S3-CHECKPOINT-STRUCTURED-EDITS) — the structured checkpoint editor. Lets a
// GUI-only author fix what the AI got wrong at a blocking checkpoint (rename/retype/DELETE a cast
// member, edit/remove a beat) WITHOUT a raw-JSON textarea and WITHOUT the deep-merge-cannot-delete
// trap: the whole list is sent back, so a removed row actually disappears (BE _merge_pass_edits,
// option A). Emits a structured `edits` patch through onSave; the rail saves it as a held revision
// (approved=false + edits), never a blind approve. Known kinds only (cast_plan / beat_plan).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PlanArtifactKind } from '../types';

type Row = Record<string, unknown>;
const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));

interface Props {
  kind: PlanArtifactKind;
  content: unknown;
  busy: boolean;
  onSave: (edits: Record<string, unknown>) => void;
  onCancel: () => void;
}

/** The field key holding the editable list, and the columns we expose, per known kind. */
const SHAPE: Partial<Record<PlanArtifactKind, { field: string; cols: { key: string; label: string }[] }>> = {
  cast_plan: { field: 'cast', cols: [{ key: 'name', label: 'Name' }, { key: 'role', label: 'Role' }, { key: 'trait', label: 'Trait' }] },
  beat_plan: { field: 'beats', cols: [{ key: 'beat', label: 'Beat' }, { key: 'tension', label: 'Tension' }, { key: 'synopsis', label: 'Synopsis' }] },
};

/** cast_plan tolerates `cast` OR `roster`; read whichever the artifact actually carries. */
function readRows(kind: PlanArtifactKind, content: unknown, field: string): Row[] {
  const obj = content as Record<string, unknown> | null;
  const raw = obj?.[field] ?? (kind === 'cast_plan' ? obj?.roster : undefined);
  return Array.isArray(raw) ? raw.map((r) => ({ ...(r as Row) })) : [];
}

export function PassArtifactEditor({ kind, content, busy, onSave, onCancel }: Props) {
  const { t } = useTranslation('studio');
  const shape = SHAPE[kind];
  const [rows, setRows] = useState<Row[]>(() => (shape ? readRows(kind, content, shape.field) : []));

  if (!shape) return null; // unknown kind → no structured editor (caller keeps the read-only view)

  const setCell = (i: number, key: string, val: string) =>
    setRows((rs) => rs.map((r, ri) => (ri === i ? { ...r, [key]: val } : r)));
  const removeRow = (i: number) => setRows((rs) => rs.filter((_, ri) => ri !== i));
  const addRow = () => setRows((rs) => [...rs, Object.fromEntries(shape.cols.map((c) => [c.key, '']))]);

  const save = () => {
    // Drop empty rows (no meaningful values) so an accidental blank add doesn't ship. Preserve any
    // fields we don't expose as columns (e.g. ids) — spread keeps them on the row.
    const cleaned = rows.filter((r) => shape.cols.some((c) => str(r[c.key]).trim() !== ''));
    onSave({ [shape.field]: cleaned });
  };

  return (
    <div data-testid="pass-artifact-editor" className="rounded border border-primary/30 bg-background/60 p-1.5">
      <div className="space-y-1">
        {rows.map((r, i) => (
          <div key={i} data-testid={`edit-row-${i}`} className="flex items-center gap-1">
            {shape.cols.map((c) => (
              <input
                key={c.key}
                data-testid={`edit-${shape.field}-${i}-${c.key}`}
                value={str(r[c.key])}
                placeholder={c.label}
                onChange={(e) => setCell(i, c.key, e.target.value)}
                className="min-w-0 flex-1 rounded border border-border bg-background px-1 py-0.5 text-[10px]"
              />
            ))}
            <button
              type="button" data-testid={`edit-remove-${i}`} onClick={() => removeRow(i)}
              title={t('planPasses.editRemove', { defaultValue: 'Remove' })}
              className="rounded border border-destructive/40 px-1 text-[10px] text-destructive hover:bg-destructive/10"
            >✕</button>
          </div>
        ))}
        {!rows.length && (
          <p className="text-[10px] text-muted-foreground">{t('planPasses.editEmpty', { defaultValue: 'Nothing here yet — add a row.' })}</p>
        )}
      </div>
      <div className="mt-1.5 flex gap-2">
        <button
          type="button" data-testid="edit-add-row" onClick={addRow}
          className="rounded border border-border px-2 py-0.5 text-[10px] hover:bg-secondary"
        >+ {t('planPasses.editAdd', { defaultValue: 'Add' })}</button>
        <button
          type="button" data-testid="edit-save" disabled={busy} onClick={save}
          className="ml-auto rounded bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
        >{t('planPasses.saveEdits', { defaultValue: 'Save edits' })}</button>
        <button
          type="button" data-testid="edit-cancel" onClick={onCancel}
          className="rounded border border-border px-2 py-0.5 text-[10px] hover:bg-secondary"
        >{t('planPasses.cancel', { defaultValue: 'Cancel' })}</button>
      </div>
    </div>
  );
}
