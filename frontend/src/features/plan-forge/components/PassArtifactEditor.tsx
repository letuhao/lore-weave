// PlanForge S3 (D-S3-CHECKPOINT-STRUCTURED-EDITS) — the structured checkpoint editor. Lets a
// GUI-only author fix what the AI got wrong at a blocking checkpoint (rename/retype/DELETE a cast
// member, re-assign a chapter's beat) WITHOUT a raw-JSON textarea and WITHOUT the
// deep-merge-cannot-delete trap: the whole list is sent back, so a removed row actually disappears
// (BE _merge_pass_edits, option A). Emits a structured `edits` patch through onSave; the rail saves
// it as a held revision (approved=false + edits), never a blind approve.
//
// THE SHAPES HERE MUST MATCH THE PRODUCER, NOT A FIXTURE.
// This file previously bound `beat_plan` to a `beats` field and `cast_plan` to a `trait` column.
// Neither is emitted by the backend — `run_beats` produces {chapters, tension_curve,
// unmapped_beats} and `run_cast` produces {name, role, archetype, summary, is_new, attributes}.
// The editor therefore rendered an empty form on every real run, and anything typed into it was
// written to a field no pass reads (while still staling the downstream passes). The unit tests
// passed the whole time because they asserted the invented shape on both sides. Shapes below were
// verified against live `plan_artifact` rows; change them only against the producer.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PlanArtifactKind } from '../types';

type Row = Record<string, unknown>;
const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));

interface Col {
  key: string;
  label: string;
  /** Render as a <select> over a closed set rather than a free-text input. */
  enumOf?: 'available_beats';
  /** Not user-editable — shown for orientation (e.g. which chapter a row is). */
  readOnly?: boolean;
}

interface Props {
  kind: PlanArtifactKind;
  content: unknown;
  busy: boolean;
  onSave: (edits: Record<string, unknown>) => void;
  onCancel: () => void;
}

/** The field key holding the editable list, and the columns we expose, per known kind. */
// EXPORTED so `planArtifactContract.test.ts` can assert THESE bindings against the producer's
// generated contract. A hand-mirrored copy in the test would just be a third place to be wrong —
// which is the exact failure mode (consumer asserting its own assumption) that let the original
// `beats`/`trait` drift ship green.
export const SHAPE: Partial<Record<PlanArtifactKind, { field: string; cols: Col[] }>> = {
  cast_plan: {
    field: 'cast',
    cols: [
      { key: 'name', label: 'Name' },
      { key: 'role', label: 'Role' },
      { key: 'archetype', label: 'Archetype' },
      { key: 'summary', label: 'Summary' },
    ],
  },
  // Shapes below are the producers' (`run_motifs` / `run_world` / `run_character_arcs`), confirmed
  // against live artifacts. Identity-ish and machine-owned fields (`code`, `is_new`, `attributes`)
  // are deliberately NOT exposed — they are preserved by the row spread on save.
  motif_plan: {
    field: 'motifs',
    cols: [
      { key: 'name', label: 'Motif' },
      // NOT an enum on purpose. `grounded_plan.motifs_for_beat` matches this by SUBSTRING and is
      // explicitly fail-open ("any UNRECOGNISED role → always offered"), so a free string cannot
      // silently drop a motif the way an unknown `beat_role` silently flattens a chapter.
      { key: 'arc_role', label: 'Arc role (spine / recurring / foil / climax payoff)' },
      { key: 'why', label: 'Why' },
    ],
  },
  world_plan: {
    field: 'entities',
    cols: [
      { key: 'name', label: 'Name' },
      { key: 'kind', label: 'Kind' },
      { key: 'summary', label: 'Summary' },
    ],
  },
  char_arc_plan: {
    field: 'character_arcs',
    cols: [
      { key: 'name', label: 'Character' },
      { key: 'role', label: 'Role' },
      { key: 'arc', label: 'Arc' },
      { key: 'introduce_at_chapter', label: 'Intro ch.' },
    ],
  },
  beat_plan: {
    field: 'chapters',
    cols: [
      // The chapter's identity — editing it here would silently re-target the row, so it is shown
      // read-only. Deleting a row is still the way to drop a chapter from the shape.
      { key: 'title', label: 'Chapter', readOnly: true },
      // A CLOSED SET. A free-text beat role is dropped by `parse_chapter_map` and falls to the
      // neutral tension band with no warning — the same silent-no-op class as an un-enumerated
      // tool arg. The options come from the artifact's own `available_beats`.
      { key: 'beat_role', label: 'Beat', enumOf: 'available_beats' },
      { key: 'intent', label: 'Intent' },
    ],
  },
};

/** cast_plan tolerates `cast` OR `roster`; read whichever the artifact actually carries. */
function readRows(kind: PlanArtifactKind, content: unknown, field: string): Row[] {
  const obj = content as Record<string, unknown> | null;
  const raw = obj?.[field] ?? (kind === 'cast_plan' ? obj?.roster : undefined);
  return Array.isArray(raw) ? raw.map((r) => ({ ...(r as Row) })) : [];
}

/** The closed set a column may choose from, off the artifact itself. */
function readEnum(content: unknown, source: string): { key: string; label: string }[] {
  const raw = (content as Record<string, unknown> | null)?.[source];
  if (!Array.isArray(raw)) return [];
  return raw
    .map((b) => {
      const o = b as Row;
      return { key: str(o?.key), label: str(o?.label) || str(o?.key) };
    })
    .filter((o) => o.key !== '');
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
    // fields we don't expose as columns (ordinal, event_id, is_new, attributes…) — spread keeps
    // them on the row, which is what makes a partial edit safe.
    const editable = shape.cols.filter((c) => !c.readOnly);
    const cleaned = rows.filter((r) => editable.some((c) => str(r[c.key]).trim() !== ''));
    onSave({ [shape.field]: cleaned });
  };

  return (
    <div data-testid="pass-artifact-editor" className="rounded border border-primary/30 bg-background/60 p-1.5">
      <div className="space-y-1">
        {rows.map((r, i) => (
          <div key={i} data-testid={`edit-row-${i}`} className="flex items-center gap-1">
            {shape.cols.map((c) => {
              const testId = `edit-${shape.field}-${i}-${c.key}`;
              if (c.readOnly) {
                return (
                  <span
                    key={c.key}
                    data-testid={testId}
                    title={str(r[c.key])}
                    className="min-w-0 flex-1 truncate px-1 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {str(r[c.key]) || '—'}
                  </span>
                );
              }
              if (c.enumOf) {
                const options = readEnum(content, c.enumOf);
                const current = str(r[c.key]);
                return (
                  <select
                    key={c.key}
                    data-testid={testId}
                    value={current}
                    onChange={(e) => setCell(i, c.key, e.target.value)}
                    className="min-w-0 flex-1 rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                  >
                    <option value="">{t('planPasses.noBeat', { defaultValue: '(no beat)' })}</option>
                    {options.map((o) => (
                      <option key={o.key} value={o.key}>{o.label}</option>
                    ))}
                    {/* A role already on the row but absent from the closed set (an older artifact,
                        or a structure that changed under it) must stay selectable — silently
                        resetting the author's data to blank would be a worse bug than showing it. */}
                    {current !== '' && !options.some((o) => o.key === current) && (
                      <option value={current}>{current} (unknown)</option>
                    )}
                  </select>
                );
              }
              return (
                <input
                  key={c.key}
                  data-testid={testId}
                  value={str(r[c.key])}
                  placeholder={c.label}
                  onChange={(e) => setCell(i, c.key, e.target.value)}
                  className="min-w-0 flex-1 rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                />
              );
            })}
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
