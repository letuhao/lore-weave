// S-04 — the EDITABLE divergence spec + overrides (replaces the old read-only block
// + "editing is not available yet" note). Render-only: all logic/mutations live in
// useDivergenceSpecEditor. Mount with `key={projectId}` so switching derivatives
// remounts with fresh form drafts (no useEffect-to-sync-props).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useDivergenceSpecEditor } from '../hooks/useDivergenceSpecEditor';
import { cn } from '@/lib/utils';
import { TOUCH_TARGET_MOBILE_ONLY_CLASS } from '@/lib/touchTarget';
import type { DivergenceTaxonomy, EntityOverrideRow } from '../types';

const TAXONOMIES: DivergenceTaxonomy[] = ['pov_shift', 'character_transform', 'au'];
// Audit fix — human labels (the select used to show the raw enum: "au", "pov_shift").
const TAXONOMY_LABELS: Record<DivergenceTaxonomy, string> = {
  pov_shift: 'POV shift',
  character_transform: 'Character transform',
  au: 'Alternate universe (AU)',
};

function overrideDescription(fields: Record<string, unknown>): string {
  return typeof fields.description === 'string' ? fields.description : '';
}

function overrideName(fields: Record<string, unknown>): string {
  return typeof fields.name === 'string' ? fields.name : '';
}

// The packer applies `name` + `description`/`summary` from an override's field-set
// (merge.py apply_entity_overrides). We expose both so a dị bản can RENAME an entity
// (e.g. a genderbend/rename AU), not only re-describe it.
function buildOverrideFields(name: string, desc: string): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  if (name.trim()) fields.name = name.trim();
  if (desc.trim()) fields.description = desc.trim();
  return fields;
}

export function DivergenceSpecEditor({
  projectId, sourceProjectId, taxonomy, povAnchor, canonRules, token,
}: {
  projectId: string;
  sourceProjectId: string | null;
  taxonomy: DivergenceTaxonomy | null;
  povAnchor: string | null;
  canonRules: string[];
  token: string | null;
}) {
  const { t } = useTranslation('composition');
  const ed = useDivergenceSpecEditor(projectId, sourceProjectId, token);
  const [tax, setTax] = useState<DivergenceTaxonomy>(taxonomy ?? 'au');
  const [pov, setPov] = useState<string | null>(povAnchor);  // local so the select doesn't snap back mid-save
  const [canonDraft, setCanonDraft] = useState(canonRules.join('\n'));
  const [addAnchor, setAddAnchor] = useState('');
  const [addName, setAddName] = useState('');
  const [addDesc, setAddDesc] = useState('');

  const canonDirty = canonDraft !== canonRules.join('\n');
  const fail = () => toast.error(t('divergence.editFailed', { defaultValue: 'Could not save — try again.' }));

  const saveTaxonomy = (next: DivergenceTaxonomy) => {
    const prev = tax;
    setTax(next);
    // Revert the optimistic select if the write fails (no success-invalidate would fix it).
    ed.patchSpec.mutate({ taxonomy: next }, { onError: () => { setTax(prev); fail(); } });
  };
  const saveCanon = () => {
    const rules = canonDraft.split('\n').map((r) => r.trim()).filter(Boolean);
    ed.patchSpec.mutate({ canon_rule: rules }, { onError: fail });
  };
  // Part A — set/re-pick (a glossary anchor) or clear (empty → null) the POV-shift character.
  // Optimistic local state so the select reflects the pick immediately; revert on error.
  const savePov = (anchorId: string) => {
    const prev = pov;
    const next = anchorId || null;
    setPov(next);
    ed.patchSpec.mutate({ pov_anchor: next }, { onError: () => { setPov(prev); fail(); } });
  };
  const doAdd = () => {
    if (!addAnchor) return;
    ed.addOverride.mutate(
      { target: addAnchor, fields: buildOverrideFields(addName, addDesc) },
      { onSuccess: () => { setAddAnchor(''); setAddName(''); setAddDesc(''); }, onError: fail },
    );
  };

  return (
    <div className="p-2.5" data-testid="divergence-spec-editor">
      <dl className="grid grid-cols-[80px_1fr] items-center gap-x-2 gap-y-2 text-[11px]">
        <dt className="text-muted-foreground">{t('divergence.taxonomy', { defaultValue: 'Taxonomy' })}</dt>
        <dd>
          <select
            data-testid="divergence-edit-taxonomy"
            className="rounded border border-border bg-transparent px-1.5 py-0.5 text-[11px]"
            value={tax}
            onChange={(e) => saveTaxonomy(e.target.value as DivergenceTaxonomy)}
            aria-label={t('divergence.taxonomy', { defaultValue: 'Taxonomy' })}
          >
            {TAXONOMIES.map((v) => (
              <option key={v} value={v}>{t(`divergence.tax_${v}`, { defaultValue: TAXONOMY_LABELS[v] })}</option>
            ))}
          </select>
        </dd>

        <dt className="text-muted-foreground">{t('divergence.povAnchor', { defaultValue: 'POV anchor' })}</dt>
        <dd className="flex items-center gap-1.5">
          {/* Part A — pick/re-pick/clear the POV-shift character. The empty option clears
              it (pov_anchor=null). Keyed on the glossary anchor — the id-space the packer
              default-fills as the effective scene POV. A stale anchor not in the source
              list falls back to a mono id so it's still visible. */}
          <select
            data-testid="divergence-pov-select"
            className="min-w-0 flex-1 rounded border border-border bg-transparent px-1.5 py-0.5 text-[11px]"
            value={pov ?? ''}
            onChange={(e) => savePov(e.target.value)}
            aria-label={t('divergence.povAnchor', { defaultValue: 'POV anchor' })}
          >
            <option value="">{t('divergence.noPov', { defaultValue: '— no POV anchor —' })}</option>
            {pov && !ed.anchoredEntities.some((e) => e.glossary_entity_id === pov) && (
              <option value={pov}>{ed.entityByAnchor.get(pov)?.name ?? pov}</option>
            )}
            {ed.anchoredEntities.map((e) => (
              <option key={e.glossary_entity_id!} value={e.glossary_entity_id!}>{e.name} ({e.kind})</option>
            ))}
          </select>
        </dd>
      </dl>

      {/* Canon rules — one per line (mirrors the wizard's Step 3 editor). */}
      <label className="mt-2 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('divergence.canonRules', { defaultValue: 'Canon rules' })}
      </label>
      <textarea
        data-testid="divergence-edit-canon"
        className="mt-1 min-h-14 w-full rounded border border-border bg-transparent px-2 py-1 text-[11px]"
        placeholder={t('divergence.canonRulesPlaceholder', { defaultValue: 'One rule per line (e.g. Magic no longer exists in this branch).' })}
        value={canonDraft}
        onChange={(e) => setCanonDraft(e.target.value)}
      />
      {canonDirty && (
        <button
          type="button"
          data-testid="divergence-canon-save"
          disabled={ed.patchSpec.isPending}
          onClick={saveCanon}
          className="mt-1 rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
        >
          {t('divergence.saveRules', { defaultValue: 'Save rules' })}
        </button>
      )}

      {/* Entity overrides — editable list + "override another entity". */}
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('divergence.overrides', { defaultValue: 'Overrides' })}
        </span>
      </div>
      <div className="mt-1 flex flex-col gap-1.5" data-testid="divergence-override-list">
        {(ed.overrides.data ?? []).length === 0 ? (
          <div className="text-[11px] text-muted-foreground" data-testid="divergence-override-empty">
            {t('divergence.noOverrides', { defaultValue: 'No entity overrides yet.' })}
          </div>
        ) : (
          (ed.overrides.data ?? []).map((o) => (
            <OverrideRow
              key={o.id}
              row={o}
              name={ed.entityByAnchor.get(o.target_entity_id)?.name ?? null}
              busy={ed.updateOverride.isPending || ed.removeOverride.isPending}
              onSave={(fields) => ed.updateOverride.mutate({ id: o.id, fields }, { onError: fail })}
              onDelete={() => ed.removeOverride.mutate(o.id, { onError: fail })}
            />
          ))
        )}
      </div>

      {/* Override another entity — only anchored (glossary) canon entities are
          offered; overriding an unanchored one silently no-ops (packer id-space). */}
      {ed.addableEntities.length > 0 && (
        <div className="mt-2 flex flex-col gap-1 rounded border border-dashed border-border p-2" data-testid="divergence-override-add">
          <select
            data-testid="divergence-override-add-entity"
            className="rounded border border-border bg-transparent px-1.5 py-0.5 text-[11px]"
            value={addAnchor}
            onChange={(e) => setAddAnchor(e.target.value)}
            aria-label={t('divergence.overrideEntity', { defaultValue: 'Entity to override' })}
          >
            <option value="">{t('divergence.pickEntity', { defaultValue: 'Override another entity…' })}</option>
            {ed.addableEntities.map((e) => (
              <option key={e.glossary_entity_id!} value={e.glossary_entity_id!}>{e.name} ({e.kind})</option>
            ))}
          </select>
          {addAnchor && (
            <>
              <input
                data-testid="divergence-override-add-name"
                className="rounded border border-border bg-transparent px-2 py-1 text-[11px]"
                placeholder={t('divergence.overrideNamePlaceholder', { defaultValue: 'New name in this dị bản (optional)…' })}
                value={addName}
                onChange={(e) => setAddName(e.target.value)}
              />
              <input
                data-testid="divergence-override-add-desc"
                className="rounded border border-border bg-transparent px-2 py-1 text-[11px]"
                placeholder={t('divergence.overridePlaceholder', { defaultValue: 'How does this entity differ (e.g. now a villain)…' })}
                value={addDesc}
                onChange={(e) => setAddDesc(e.target.value)}
              />
              <button
                type="button"
                data-testid="divergence-override-add-save"
                // Require at least one field — an empty {} override is a no-op that just
                // consumes the (work,target) unique slot (the user would edit it anyway).
                disabled={ed.addOverride.isPending || !(addName.trim() || addDesc.trim())}
                onClick={doAdd}
                className="self-start rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
              >
                {t('divergence.addOverride', { defaultValue: 'Add override' })}
              </button>
            </>
          )}
        </div>
      )}
      {/* Audit fix — when the source has NO glossary-anchored entities, the override picker
          + POV picker are both empty. Explain WHY instead of silently showing nothing. */}
      {ed.anchoredEntities.length === 0 && (
        <div data-testid="divergence-no-anchors" className="mt-2 rounded border border-dashed border-border p-2 text-[11px] text-muted-foreground">
          {t('divergence.noAnchoredEntities', { defaultValue: 'No glossary-anchored characters in this branch’s source yet — anchor entities in the glossary to set a POV or override them here.' })}
        </div>
      )}
    </div>
  );
}

function OverrideRow({
  row, name, busy, onSave, onDelete,
}: {
  row: EntityOverrideRow;
  name: string | null;
  busy: boolean;
  onSave: (fields: Record<string, unknown>) => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation('composition');
  const [nameField, setNameField] = useState(overrideName(row.overridden_fields));
  const [desc, setDesc] = useState(overrideDescription(row.overridden_fields));
  const [confirmingDelete, setConfirmingDelete] = useState(false);  // H-4b — lightweight inline confirm
  const dirty = nameField !== overrideName(row.overridden_fields) || desc !== overrideDescription(row.overridden_fields);
  return (
    <div data-testid={`divergence-override-row-${row.id}`} className="flex flex-col gap-1 rounded border border-border px-2 py-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium">
          {name ?? <span className="font-mono text-[10px] text-muted-foreground">{row.target_entity_id}</span>}
        </span>
        {confirmingDelete ? (
          // H-4b — two-step inline confirm (not a modal; low stakes, re-addable).
          <span className="flex shrink-0 items-center gap-1 text-[10px]">
            <span className="text-muted-foreground">{t('divergence.removeConfirm', { defaultValue: 'Remove?' })}</span>
            <button
              type="button" data-testid={`divergence-override-delete-confirm-${row.id}`}
              disabled={busy} onClick={onDelete}
              className={cn('rounded px-1.5 py-0.5 font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-950/30', TOUCH_TARGET_MOBILE_ONLY_CLASS)}
            >{t('divergence.yes', { defaultValue: 'Yes' })}</button>
            <button
              type="button" data-testid={`divergence-override-delete-cancel-${row.id}`}
              onClick={() => setConfirmingDelete(false)}
              className={cn('rounded px-1.5 py-0.5 text-muted-foreground hover:bg-muted', TOUCH_TARGET_MOBILE_ONLY_CLASS)}
            >{t('divergence.no', { defaultValue: 'No' })}</button>
          </span>
        ) : (
          <button
            type="button"
            data-testid={`divergence-override-delete-${row.id}`}
            disabled={busy}
            onClick={() => setConfirmingDelete(true)}
            className={cn('shrink-0 rounded px-1.5 py-0.5 text-[10px] text-red-600 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-950/30', TOUCH_TARGET_MOBILE_ONLY_CLASS)}
          >
            {t('divergence.remove', { defaultValue: 'Remove' })}
          </button>
        )}
      </div>
      <input
        data-testid={`divergence-override-name-${row.id}`}
        className="rounded border border-border bg-transparent px-2 py-1 text-[11px]"
        value={nameField}
        onChange={(e) => setNameField(e.target.value)}
        placeholder={t('divergence.overrideNamePlaceholder', { defaultValue: 'New name in this dị bản (optional)…' })}
      />
      <input
        data-testid={`divergence-override-desc-${row.id}`}
        className="rounded border border-border bg-transparent px-2 py-1 text-[11px]"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        placeholder={t('divergence.overridePlaceholder', { defaultValue: 'How does this entity differ…' })}
      />
      {dirty && (
        <button
          type="button"
          data-testid={`divergence-override-save-${row.id}`}
          disabled={busy}
          onClick={() => onSave(buildOverrideFields(nameField, desc))}
          className="self-start rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
        >
          {t('divergence.save', { defaultValue: 'Save' })}
        </button>
      )}
    </div>
  );
}
