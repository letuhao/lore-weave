import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UserModel } from '@/features/settings/api';
import { isRecookable } from '../types';
import type { Source, IngestResult } from '../types';

/** One corpus card with its own ingest form. Register creates an empty shell;
 *  ingest chunks + REAL-embeds text into it (the recook/retrieval material).
 *  Embed-model options come from provider-registry (no hardcoded names). */
export function SourceCard({
  source,
  embeds,
  onIngest,
  busy,
}: {
  source: Source;
  embeds: UserModel[];
  onIngest: (
    corpusId: string,
    body: { text: string; embedding_model_ref: string },
  ) => Promise<IngestResult | null>;
  busy?: boolean;
}) {
  const { t } = useTranslation('enrichment');
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [embedModel, setEmbedModel] = useState('');
  const ok = isRecookable(source.license);
  const canIngest = !!text.trim() && !!embedModel && !busy;

  const submit = async () => {
    if (!text.trim() || !embedModel) return;
    const r = await onIngest(source.corpus_id, {
      text: text.trim(),
      embedding_model_ref: embedModel,
    });
    if (r) {
      setOpen(false);
      setText('');
    }
  };

  return (
    <div className={cn('rounded-lg border bg-card px-4 py-3', !ok && 'opacity-80')} data-testid="enrichment-source-card">
      <div className="flex items-center justify-between">
        <span className="font-serif font-medium">{source.name}</span>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[10px] font-medium',
            ok ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive',
          )}
        >
          {t(`license.${source.license}`, { defaultValue: source.license })}
        </span>
      </div>
      <p className="mt-1 font-mono text-[11px] text-muted-foreground">
        kind={source.kind} · {ok ? t('sources.recook_ok') : t('sources.recook_refused')}
        {source.chunk_count != null && <> · {t('sources.chunks', { count: source.chunk_count })}</>}
      </p>

      <div className="mt-2">
        <button
          onClick={() => setOpen(!open)}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
        >
          <Upload className="h-3 w-3" /> {t('sources.ingest')}
        </button>
      </div>

      {open && (
        <div className="mt-2 space-y-2 rounded-md border bg-background p-2 text-xs">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            placeholder={t('sources.ingest_placeholder')}
            data-testid="enrichment-ingest-text"
            className="w-full rounded border bg-background p-2 font-serif focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">{t('sources.embed_model')}</span>
              <select
                value={embedModel}
                onChange={(e) => setEmbedModel(e.target.value)}
                className="rounded border bg-background px-2 py-1"
              >
                <option value="">{t('gaps.select_model')}</option>
                {embeds.map((m) => (
                  <option key={m.user_model_id} value={m.user_model_id}>
                    {m.alias || m.provider_model_name}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => void submit()}
              disabled={!canIngest}
              className="rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground disabled:opacity-50"
            >
              {busy ? t('sources.ingesting') : t('actions.save')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
