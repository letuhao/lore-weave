// C24 (dị bản M0) — the 4 wizard step bodies (views — render only). Step state is
// owned by useDivergenceWizard; these receive it via props. Steps render via
// INTERNAL BRANCHING in DivergenceWizard (CSS-hidden / single-active) — never a
// ternary that UNMOUNTS the others (that would destroy in-flight draft state).
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { booksApi } from '../../books/api';
import { knowledgeApi } from '../../knowledge/api';
import type { DivergenceTaxonomy } from '../types';
import type { OverrideDraft } from '../hooks/useDivergenceWizard';

const TAXONOMIES: { value: DivergenceTaxonomy; emoji: string; key: string; def: string }[] = [
  { value: 'pov_shift', emoji: '👁️', key: 'typePovShift', def: 'POV shift' },
  { value: 'character_transform', emoji: '🔁', key: 'typeCharacterTransform', def: 'Character transform' },
  { value: 'au', emoji: '🌌', key: 'typeAu', def: 'Alternate universe' },
];

// ── Step 1: source confirm + chapter-level branch point (G3) ──────────────────
export function Step1Source({
  bookId, branchPoint, setBranchPoint, token,
}: {
  bookId: string; branchPoint: number | null; setBranchPoint: (n: number | null) => void; token: string | null;
}) {
  const { t } = useTranslation('composition');
  const chapters = useQuery({
    queryKey: ['composition', 'derive-chapters', bookId],
    queryFn: () => booksApi.listChapters(token!, bookId, { lifecycle_state: 'active', limit: 500, offset: 0 }),
    enabled: !!bookId && !!token,
    select: (d) => [...d.items].sort((a, b) => a.sort_order - b.sort_order),
  });
  return (
    <div className="flex flex-col gap-3" data-testid="divergence-step-1">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        {t('derive.step1Hint', { defaultValue: 'Pick the chapter where your dị bản branches from canon. Everything up to that chapter is inherited read-only; you write forward from there.' })}
      </p>
      <label className="text-xs font-medium uppercase tracking-wide text-neutral-500">
        {t('derive.branchPoint', { defaultValue: 'Branch point (chapter)' })}
      </label>
      <select
        data-testid="divergence-branch-point"
        className="rounded border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-600"
        value={branchPoint ?? ''}
        onChange={(e) => setBranchPoint(e.target.value === '' ? null : Number(e.target.value))}
        aria-label={t('derive.branchPoint', { defaultValue: 'Branch point (chapter)' })}
      >
        <option value="">{t('derive.branchFromStart', { defaultValue: 'From the very start (no inherited canon)' })}</option>
        {(chapters.data ?? []).map((c) => (
          <option key={c.chapter_id} value={c.sort_order}>
            {c.sort_order + 1}. {c.title || c.original_filename}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── Step 2: divergence type (UX §7.1) ─────────────────────────────────────────
export function Step2Type({
  taxonomy, setTaxonomy,
}: {
  taxonomy: DivergenceTaxonomy; setTaxonomy: (t: DivergenceTaxonomy) => void;
}) {
  const { t } = useTranslation('composition');
  return (
    <div className="flex flex-col gap-2" data-testid="divergence-step-2">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        {t('derive.step2Hint', { defaultValue: 'How does your version diverge? (You can still override any entity in the next step.)' })}
      </p>
      {TAXONOMIES.map((tax) => (
        <button
          key={tax.value}
          type="button"
          data-testid={`divergence-type-${tax.value}`}
          aria-pressed={taxonomy === tax.value}
          onClick={() => setTaxonomy(tax.value)}
          className={
            'flex items-center gap-3 rounded border px-3 py-2 text-left text-sm ' +
            (taxonomy === tax.value
              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950'
              : 'border-neutral-300 dark:border-neutral-600')
          }
        >
          <span aria-hidden className="text-lg">{tax.emoji}</span>
          <span>{t(`derive.${tax.key}`, { defaultValue: tax.def })}</span>
        </button>
      ))}
    </div>
  );
}

// ── Step 3: overrides preview (entity-field overrides + canon rules) ──────────
export function Step3Overrides({
  sourceProjectId, overrides, setOverride, canonRules, setCanonRules, token,
}: {
  sourceProjectId: string;
  overrides: OverrideDraft;
  setOverride: (id: string, fields: Record<string, unknown> | null) => void;
  canonRules: string[];
  setCanonRules: (rules: string[]) => void;
  token: string | null;
}) {
  const { t } = useTranslation('composition');
  const entities = useQuery({
    queryKey: ['composition', 'derive-entities', sourceProjectId],
    queryFn: () => knowledgeApi.listEntities({ project_id: sourceProjectId, limit: 50, sort_by: 'mention_count' }, token!),
    enabled: !!sourceProjectId && !!token,
    select: (d) => d.entities,
  });
  return (
    <div className="flex flex-col gap-3" data-testid="divergence-step-3">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        {t('derive.step3Hint', { defaultValue: 'Override entity fields for your dị bản. Anything you do NOT override is inherited from canon.' })}
      </p>
      <div className="max-h-52 overflow-y-auto rounded border border-neutral-200 dark:border-neutral-700">
        {(entities.data ?? []).map((e) => {
          // ID-SPACE (C24 fix): the packer's present-lens keys overrides on the
          // GLOSSARY anchor (`glossary_entity_id`), NOT the knowledge node id
          // (`e.id`). Capture the override target as the anchor for an anchored
          // (canonical) entity. An UNANCHORED (discovered) entity has no anchor to
          // key on — overriding it would write the knowledge node id, which the
          // present-lens never matches (the override would silently no-op). So we
          // DISALLOW it with a clear hint (anchor it first via the Entities tab),
          // rather than writing an id-space the packer can't resolve.
          const anchorId = e.glossary_entity_id;
          const anchored = Boolean(anchorId);
          const ov = anchorId ? overrides[anchorId] : undefined;
          const desc = typeof ov?.description === 'string' ? (ov.description as string) : '';
          return (
            <div key={e.id} data-testid={`divergence-entity-row-${e.id}`} className="flex flex-col gap-1 border-b border-neutral-100 px-2 py-1.5 text-sm last:border-0 dark:border-neutral-800">
              <div className="flex items-center justify-between">
                <span className="font-medium">{e.name} <span className="text-xs text-neutral-400">({e.kind})</span></span>
                {ov && <span data-testid={`divergence-overridden-${anchorId}`} className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-900 dark:text-amber-200">{t('derive.overridden', { defaultValue: 'Overridden' })}</span>}
              </div>
              {anchored ? (
                <input
                  data-testid={`divergence-override-input-${anchorId}`}
                  className="rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
                  placeholder={t('derive.overridePlaceholder', { defaultValue: 'Override this entity (e.g. now a woman, now a villain)…' })}
                  value={desc}
                  onChange={(ev) => setOverride(anchorId!, ev.target.value.trim() ? { description: ev.target.value } : null)}
                />
              ) : (
                <p data-testid={`divergence-unanchored-hint-${e.id}`} className="text-xs text-neutral-500 dark:text-neutral-400">
                  {t('derive.unanchoredHint', { defaultValue: 'This entity is not yet in the glossary — promote it (Entities tab) before you can override it here.' })}
                </p>
              )}
            </div>
          );
        })}
        {entities.data?.length === 0 && (
          <p className="px-2 py-3 text-xs text-neutral-500">{t('derive.noEntities', { defaultValue: 'No canon entities yet — author overrides later in the studio.' })}</p>
        )}
      </div>
      <label className="text-xs font-medium uppercase tracking-wide text-neutral-500">{t('derive.canonRules', { defaultValue: 'Added canon rules (one per line)' })}</label>
      <textarea
        data-testid="divergence-canon-rules"
        className="min-h-16 rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
        placeholder={t('derive.canonRulesPlaceholder', { defaultValue: 'e.g. Magic no longer exists in this branch.' })}
        value={canonRules.join('\n')}
        onChange={(e) => setCanonRules(e.target.value.split('\n'))}
      />
    </div>
  );
}

// ── Step 4: name → submit ─────────────────────────────────────────────────────
export function Step4Name({
  name, setName,
}: {
  name: string; setName: (s: string) => void;
}) {
  const { t } = useTranslation('composition');
  return (
    <div className="flex flex-col gap-2" data-testid="divergence-step-4">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">{t('derive.step4Hint', { defaultValue: 'Name your dị bản.' })}</p>
      <input
        data-testid="divergence-name"
        className="rounded border border-neutral-300 bg-transparent px-2 py-1.5 text-sm dark:border-neutral-600"
        placeholder={t('derive.namePlaceholder', { defaultValue: 'e.g. Genderbend AU — 张若尘 as a woman' })}
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-label={t('derive.name', { defaultValue: 'Dị bản name' })}
      />
    </div>
  );
}
