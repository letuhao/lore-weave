import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../../../knowledge/api';
import { ModelRolePicker } from '../ModelRolePicker';
import { ROLE_CAPABILITY, needsEmbeddingConfirm, type ModelRole } from '../../types';
import type { WizardForm } from '../../hooks/useCampaignWizard';

interface Props {
  form: WizardForm;
  setPick: (role: ModelRole, ref: string | null) => void;
  setField: <K extends keyof WizardForm>(key: K, value: WizardForm[K]) => void;
}

/** Step 3 (view): the 6-role Model Matrix. Core (extractor, translator) is always
 *  visible; the rest live under Advanced. The embedding override surfaces a
 *  destructive-confirm checkbox when the chosen project already has a graph. */
export function ModelMatrixStep({ form, setPick, setField }: Props) {
  const { t } = useTranslation('campaigns');
  const { accessToken } = useAuth();
  const [advanced, setAdvanced] = useState(false);

  const projects = useQuery({
    queryKey: ['campaign-wizard', 'projects'],
    queryFn: () => knowledgeApi.listProjects({ limit: 200 }, accessToken!),
    enabled: !!accessToken,
  });
  const project = projects.data?.items.find((p) => p.project_id === form.projectId);

  // Changing embedding on a project that already has a graph deletes its vectors.
  const showEmbeddingConfirm = needsEmbeddingConfirm(project, form.picks.embedding);

  const label = (role: ModelRole, fallback: string) =>
    t(`matrix.role.${role}`, { defaultValue: fallback });

  return (
    <div className="flex flex-col gap-4">
      {/* Core */}
      <ModelRolePicker
        capability={ROLE_CAPABILITY.extractor}
        label={label('extractor', 'Extractor (knowledge) — required')}
        value={form.picks.extractor}
        onChange={(v) => setPick('extractor', v)}
      />
      <ModelRolePicker
        capability={ROLE_CAPABILITY.translator}
        label={label('translator', 'Translator — required')}
        value={form.picks.translator}
        onChange={(v) => setPick('translator', v)}
      />
      {project && (
        <p className="text-[11px] text-muted-foreground">
          {t('matrix.projectEmbedding', {
            defaultValue: "Project embedding: {{model}} · reranker: {{rerank}}",
            model: project.embedding_model ?? t('matrix.unset', { defaultValue: 'unset' }),
            rerank: project.rerank_model ?? t('matrix.unset', { defaultValue: 'unset' }),
          })}
        </p>
      )}

      {/* Advanced */}
      <button
        type="button"
        onClick={() => setAdvanced((a) => !a)}
        className="flex items-center gap-1 self-start text-sm font-medium text-primary"
      >
        {advanced ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {t('matrix.advanced', { defaultValue: 'Advanced models (optional)' })}
      </button>

      {advanced && (
        <div className="flex flex-col gap-4 border-l-2 border-border pl-4">
          <ModelRolePicker
            capability={ROLE_CAPABILITY.verifier}
            label={label('verifier', 'Verifier (V3) — falls back to translator')}
            value={form.picks.verifier}
            onChange={(v) => setPick('verifier', v)}
          />
          <ModelRolePicker
            capability={ROLE_CAPABILITY.eval_judge}
            label={label('eval_judge', 'Eval judge (fidelity) — optional')}
            value={form.picks.eval_judge}
            onChange={(v) => setPick('eval_judge', v)}
          />
          <ModelRolePicker
            capability={ROLE_CAPABILITY.embedding}
            label={label('embedding', 'Embedding override — applied to the project')}
            value={form.picks.embedding}
            onChange={(v) => setPick('embedding', v)}
          />
          <ModelRolePicker
            capability={ROLE_CAPABILITY.reranker}
            label={label('reranker', 'Reranker override — applied to the project')}
            value={form.picks.reranker}
            onChange={(v) => setPick('reranker', v)}
          />
          {showEmbeddingConfirm && (
            <label className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={form.confirmEmbeddingChange}
                onChange={(e) => setField('confirmEmbeddingChange', e.target.checked)}
              />
              <span className="flex flex-col gap-1 text-[11px]">
                <span className="flex items-center gap-1 font-medium text-destructive">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {t('matrix.embeddingWarnTitle', { defaultValue: 'This deletes the project’s existing knowledge graph' })}
                </span>
                <span className="text-muted-foreground">
                  {t('matrix.embeddingWarnBody', { defaultValue: 'Changing the embedding model re-embeds from scratch. Confirm to proceed, or pick an empty project.' })}
                </span>
              </span>
            </label>
          )}
        </div>
      )}
    </div>
  );
}
