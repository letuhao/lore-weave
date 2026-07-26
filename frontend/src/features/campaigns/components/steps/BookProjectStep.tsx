import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { BookPicker } from '@/components/shared/BookPicker';
import { LanguagePicker } from '@/components/shared';
import { knowledgeApi } from '../../../knowledge/api';
import type { WizardForm } from '../../hooks/useCampaignWizard';

interface Props {
  form: WizardForm;
  setField: <K extends keyof WizardForm>(key: K, value: WizardForm[K]) => void;
}

/** Step 1 (view): name the campaign, pick the book + knowledge project + target
 *  language. The picked project carries the embedding/rerank vector space. */
export function BookProjectStep({ form, setField }: Props) {
  const { t } = useTranslation('campaigns');
  const { accessToken } = useAuth();

  const projects = useQuery({
    queryKey: ['campaign-wizard', 'projects'],
    // knowledge /projects caps limit at 100 (>100 → 422, which silently emptied
    // the dropdown and made the wizard unusable — Next never enabled).
    queryFn: () => knowledgeApi.listProjects({ limit: 100 }, accessToken!),
    enabled: !!accessToken,
  });

  const fieldCls = 'rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring';

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('fields.name', { defaultValue: 'Campaign name' })}
        </span>
        <input
          className={fieldCls}
          value={form.name}
          onChange={(e) => setField('name', e.target.value)}
          placeholder={t('fields.namePlaceholder', { defaultValue: 'e.g. Translate Book 1 → Vietnamese' })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('fields.book', { defaultValue: 'Book' })}
        </span>
        {/* C4 (BL-3/G6): searchable book picker — scales past the 200-cap <select>;
            emits book_id, empty stays valid (book optional). */}
        <BookPicker
          value={form.bookId ?? null}
          onChange={(id) => setField('bookId', id)}
          placeholder={t('fields.bookNone', { defaultValue: 'Search your books by title…' })}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('fields.project', { defaultValue: 'Knowledge project' })}
        </span>
        <select
          className={fieldCls}
          value={form.projectId ?? ''}
          onChange={(e) => setField('projectId', e.target.value || null)}
        >
          <option value="">{t('fields.projectNone', { defaultValue: 'Select a project…' })}</option>
          {(projects.data?.items ?? []).map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name}{p.embedding_model ? '' : ` — ${t('fields.projectNoEmbedding', { defaultValue: 'no embedding model' })}`}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-muted-foreground">
          {t('fields.projectHint', { defaultValue: 'Extraction writes into this project. Its embedding/reranker can be overridden in the Models step.' })}
        </span>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('fields.targetLanguage', { defaultValue: 'Target language (optional)' })}
        </span>
        <LanguagePicker
          className={fieldCls}
          value={form.targetLanguage}
          onChange={(code) => setField('targetLanguage', code)}
          placeholder={t('fields.targetLanguageAny', { defaultValue: 'Use your translation settings' })}
        />
      </label>
    </div>
  );
}
