import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '../../../books/api';
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

  const books = useQuery({
    queryKey: ['campaign-wizard', 'books'],
    queryFn: () => booksApi.listBooks(accessToken!, { limit: 200 }),
    enabled: !!accessToken,
  });
  const projects = useQuery({
    queryKey: ['campaign-wizard', 'projects'],
    queryFn: () => knowledgeApi.listProjects({ limit: 200 }, accessToken!),
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
        <select
          className={fieldCls}
          value={form.bookId ?? ''}
          onChange={(e) => setField('bookId', e.target.value || null)}
        >
          <option value="">{t('fields.bookNone', { defaultValue: 'Select a book…' })}</option>
          {(books.data?.items ?? []).map((b) => (
            <option key={b.book_id} value={b.book_id}>{b.title}</option>
          ))}
        </select>
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
        <input
          className={fieldCls}
          value={form.targetLanguage}
          onChange={(e) => setField('targetLanguage', e.target.value)}
          placeholder={t('fields.targetLanguagePlaceholder', { defaultValue: 'e.g. vi — blank uses your translation settings' })}
        />
      </label>
    </div>
  );
}
