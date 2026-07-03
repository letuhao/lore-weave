import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';
import { readBackendError } from '../lib/readBackendError';
import {
  PROMPT_MAX_LEN,
  PROMPT_OPS,
  type ExtractionConfigPayload,
  type FilterCategory,
  type PartialPolicy,
  type Project,
  type PromptOp,
} from '../types';

// B2-C controller for the per-novel extraction-tuning panel.
//
// Surfaces the FULLY-WIRED levers: precision filter (enabled / categories /
// partial-policy / model), entity recovery (enabled), and per-op raw system
// prompts. The precision-filter MODEL is now exposed via a provider-registry
// picker (D-WX-PRECISION-FILTER-MODEL-ARCH — it used to come from a hardcoded
// platform env UUID that 404'd cross-tenant); empty = reuse the extraction model.
//
// PUT-replace contract: the BE replaces extraction_config wholesale, so on save
// we READ-MODIFY-WRITE — start from the project's existing config (preserving
// keys we don't expose, e.g. llm_model) and overlay only the edited sections.

const ALL_CATEGORIES: FilterCategory[] = ['entity', 'relation', 'event'];

interface Draft {
  // KN model-roles — the project's DEFAULT LLM (extraction_config.llm_model). The
  // fallback every unset extraction role resolves to (role override → this →
  // user-global default → env). null = no project default (roles fall to the
  // user-global default / this job's extraction model).
  defaultModelRef: string | null;
  filterEnabled: boolean;
  filterCategories: FilterCategory[];
  filterPartialPolicy: PartialPolicy;
  // Precision-filter model: a provider-registry user_model_id, or null = reuse
  // the extraction model (the BE resolves the fallback per-user). NEVER an env model.
  filterModelRef: string | null;
  recoveryEnabled: boolean;
  // KN model-roles — entity-recovery classifier model; null = use the default
  // (the BE resolves role override → project default → user-global → env).
  recoveryModelRef: string | null;
  autocreateEnabled: boolean;
  prompts: Record<PromptOp, string>; // per-op system text ('' = no override)
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

function deriveDraft(config: Record<string, unknown>): Draft {
  const llm = asRecord(config.llm_model);
  const pf = asRecord(config.precision_filter);
  const er = asRecord(config.entity_recovery);
  const ac = asRecord(config.writer_autocreate);
  const promptsCfg = asRecord(config.prompts);
  const prompts = {} as Record<PromptOp, string>;
  for (const op of PROMPT_OPS) {
    const sys = asRecord(promptsCfg[op]).system;
    prompts[op] = typeof sys === 'string' ? sys : '';
  }
  return {
    defaultModelRef: typeof llm.model_ref === 'string' ? llm.model_ref : null,
    // A project with NO precision_filter override is treated as "off" in the
    // panel (the global default decides at run time); toggling on sends an
    // explicit override.
    filterEnabled: pf.enabled === true,
    filterCategories: Array.isArray(pf.categories)
      ? (pf.categories as FilterCategory[])
      : ALL_CATEGORIES,
    filterPartialPolicy: pf.partial_policy === 'drop' ? 'drop' : 'keep',
    filterModelRef: typeof pf.model_ref === 'string' ? pf.model_ref : null,
    recoveryEnabled: er.enabled === true,
    recoveryModelRef: typeof er.model_ref === 'string' ? er.model_ref : null,
    autocreateEnabled: ac.enabled === true,
    prompts,
  };
}

export function useExtractionConfig(project: Project, open: boolean, onChanged: () => void) {
  const { t } = useTranslation('knowledge');
  const { accessToken } = useAuth();
  const [draft, setDraft] = useState<Draft>(() => deriveDraft(project.extraction_config));
  const [submitting, setSubmitting] = useState(false);

  // Reset to the project's current config each time the dialog opens — picks up
  // any external change made while it was closed.
  useEffect(() => {
    if (!open) return;
    setDraft(deriveDraft(project.extraction_config));
    setSubmitting(false);
  }, [open, project.extraction_config]);

  const setField = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const toggleCategory = (cat: FilterCategory) =>
    setDraft((d) => ({
      ...d,
      filterCategories: d.filterCategories.includes(cat)
        ? d.filterCategories.filter((c) => c !== cat)
        : [...d.filterCategories, cat],
    }));

  const setPrompt = (op: PromptOp, system: string) =>
    setDraft((d) => ({ ...d, prompts: { ...d.prompts, [op]: system } }));

  // Filter requires ≥1 category when enabled (BE rejects an empty list).
  const filterCategoriesInvalid = draft.filterEnabled && draft.filterCategories.length === 0;
  // Block save on an over-length prompt rather than burning a guaranteed-422
  // round-trip (the BE caps each field at PROMPT_MAX_LEN).
  const anyPromptTooLong = PROMPT_OPS.some((op) => draft.prompts[op].length > PROMPT_MAX_LEN);
  const canSubmit = !submitting && !filterCategoriesInvalid && !anyPromptTooLong;

  function buildPayload(): ExtractionConfigPayload {
    // Read-modify-write: preserve unmanaged keys (rerank knobs).
    const payload: ExtractionConfigPayload = {
      ...(project.extraction_config as ExtractionConfigPayload),
    };
    // KN model-roles — the project DEFAULT LLM. Set = the fallback every unset
    // role resolves to; cleared = no project default (roles fall to the
    // user-global default / this job's extraction model).
    if (draft.defaultModelRef) {
      payload.llm_model = { model_ref: draft.defaultModelRef, model_source: 'user_model' };
    } else {
      delete payload.llm_model;
    }
    if (draft.filterEnabled) {
      const pf: Record<string, unknown> = {
        ...asRecord(project.extraction_config.precision_filter),
        enabled: true,
        categories: draft.filterCategories,
        partial_policy: draft.filterPartialPolicy,
      };
      // Explicit per-user filter model, or clear it so the BE reuses the
      // extraction model (D-WX-PRECISION-FILTER-MODEL-ARCH — never an env model).
      if (draft.filterModelRef) {
        pf.model_ref = draft.filterModelRef;
        pf.model_source = 'user_model';
      } else {
        delete pf.model_ref;
        delete pf.model_source;
      }
      payload.precision_filter = pf as ExtractionConfigPayload['precision_filter'];
    } else {
      // Explicit disable so the BE turns the filter OFF for this project.
      payload.precision_filter = { enabled: false };
    }
    const er: Record<string, unknown> = {
      ...asRecord(project.extraction_config.entity_recovery),
      enabled: draft.recoveryEnabled,
    };
    // Explicit per-project recovery model, or clear it so the BE resolves the
    // fallback (project default → user-global → env). Never an env model here.
    if (draft.recoveryEnabled && draft.recoveryModelRef) {
      er.model_ref = draft.recoveryModelRef;
      er.model_source = 'user_model';
    } else {
      delete er.model_ref;
      delete er.model_source;
    }
    payload.entity_recovery = er as ExtractionConfigPayload['entity_recovery'];
    payload.writer_autocreate = { enabled: draft.autocreateEnabled };
    const prompts: ExtractionConfigPayload['prompts'] = {};
    for (const op of PROMPT_OPS) {
      const sys = draft.prompts[op];
      if (sys && sys.trim()) prompts[op] = { system: sys };
    }
    if (Object.keys(prompts).length > 0) payload.prompts = prompts;
    else delete payload.prompts;
    return payload;
  }

  const handleSave = async (onDone: () => void) => {
    if (!accessToken || !canSubmit) return;
    setSubmitting(true);
    try {
      await knowledgeApi.updateExtractionConfig(
        project.project_id,
        buildPayload(),
        accessToken,
        project.version,
      );
      toast.success(t('projects.extractionTuning.saved'));
      onChanged();
      onDone();
    } catch (err) {
      toast.error(
        t('projects.extractionTuning.failed', { error: readBackendError(err) }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const promptLengths = useMemo(
    () =>
      Object.fromEntries(PROMPT_OPS.map((op) => [op, draft.prompts[op].length])) as Record<
        PromptOp,
        number
      >,
    [draft.prompts],
  );

  return {
    draft,
    submitting,
    canSubmit,
    filterCategoriesInvalid,
    promptLengths,
    setField,
    toggleCategory,
    setPrompt,
    handleSave,
  };
}
