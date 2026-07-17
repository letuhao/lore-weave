// S-04 — the EDITABLE divergence spec + overrides (replaces the old read-only block
// + "editing is not available yet" note). Render-only: all logic/mutations live in
// useDivergenceSpecEditor. Mount with `key={projectId}` so switching derivatives
// remounts with fresh form drafts (no useEffect-to-sync-props).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useDivergenceSpecEditor } from '../hooks/useDivergenceSpecEditor';
import type { DivergenceTaxonomy, EntityOverrideRow } from '../types';

const TAXONOMIES: DivergenceTaxonomy[] = ['pov_shift', 'character_transform', 'au'];

function overrideDescription(fields: Record<string, unknown>): string {
  return typeof fields.description === 'string' ? fields.description : '';
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
  const [canonDraft, setCanonDraft] = useState(canonRules.join('\n'));
  const [addAnchor, setAddAnchor] = useState('');
  const [addDesc, setAddDesc] = useState('');

  const canonDirty = canonDraft !== canonRules.join('\n');
  const fail = () => toast.error(t('divergence.editFailed', { defaultValue: 'Could not save — try again.' }));

  const saveTaxonomy = (next: DivergenceTaxonomy) => {
    setTax(next);
    ed.patchSpec.mutate({ taxonomy: next }, { onError: fail });
  };
  const saveCanon = () => {
    const rules = canonDraft.split('\n').map((r) => r.trim()).filter(Boolean);
    ed.patchSpec.mutate({ canon_rule: rules }, { onError: fail });
  };
  const clearPov = () => ed.patchSpec.mutate({ pov_anchor: null }, { onError: fail });
  const doAdd = () => {
    if (!addAnchor) return;
    ed.addOverride.mutate(
      { target: addAnchor, fields: addDesc.trim() ? { description: addDesc.trim() } : {} },
      { onSuccess: () => { setAddAnchor(''); setAddDesc(''); }, onError: fail },
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
              <option key={v} value={v}>{t(`divergence.tax_${v}`, { defaultValue: v })}</option>
            ))}
          </select>
        </dd>

        <dt className="text-muted-foreground">{t('divergence.povAnchor', { defaultValue: 'POV anchor' })}</dt>
        <dd className="flex items-center gap-1.5">
          <span data-testid="divergence-edit-pov" className="truncate font-mono text-[10px]">{povAnchor ?? '—'}</span>
          {povAnchor && (
            <button
              type="button"
              data-testid="divergence-pov-clear"
              onClick={clearPov}
              className="rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-muted"
            >
              {t('divergence.clear', { defaultValue: 'Clear' })}
            </button>
          )}
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
                data-testid="divergence-override-add-desc"
                className="rounded border border-border bg-transparent px-2 py-1 text-[11px]"
                placeholder={t('divergence.overridePlaceholder', { defaultValue: 'How does this entity differ (e.g. now a villain)…' })}
                value={addDesc}
                onChange={(e) => setAddDesc(e.target.value)}
              />
              <button
                type="button"
                data-testid="divergence-override-add-save"
                // Require a description — an empty {} override is a no-op that just
                // consumes the (work,target) unique slot (the user would edit it anyway).
                disabled={ed.addOverride.isPending || !addDesc.trim()}
                onClick={doAdd}
                className="self-start rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
              >
                {t('divergence.addOverride', { defaultValue: 'Add override' })}
              </button>
            </>
          )}
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
  const [desc, setDesc] = useState(overrideDescription(row.overridden_fields));
  const dirty = desc !== overrideDescription(row.overridden_fields);
  return (
    <div data-testid={`divergence-override-row-${row.id}`} className="flex flex-col gap-1 rounded border border-border px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="truncate text-[11px] font-medium">
          {name ?? <span className="font-mono text-[10px] text-muted-foreground">{row.target_entity_id}</span>}
        </span>
        <button
          type="button"
          data-testid={`divergence-override-delete-${row.id}`}
          disabled={busy}
          onClick={onDelete}
          className="rounded px-1.5 py-0.5 text-[10px] text-red-600 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-950/30"
        >
          {t('divergence.remove', { defaultValue: 'Remove' })}
        </button>
      </div>
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
          onClick={() => onSave(desc.trim() ? { description: desc.trim() } : {})}
          className="self-start rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground disabled:opacity-50"
        >
          {t('divergence.save', { defaultValue: 'Save' })}
        </button>
      )}
    </div>
  );
}
